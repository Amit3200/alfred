"""Direct Slack board create and follow-up tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from backend.models.config import AlfredConfig, SlackBoardColumnMap, SlackBoardProfile, SlackBoardWorkflowsConfig, SlackConfig
from backend.models.task import Task
from backend.routing.slack_board.direct import (
    extract_board_create_fields,
    extract_board_update_fields,
    try_slack_board_create_direct,
    try_slack_board_status_followup,
    try_slack_board_update_direct,
    try_slack_board_where_direct,
)
from backend.routing.slack_board.intent import (
    extract_list_id_override,
    extract_task_title,
    is_placeholder_list_id,
    looks_like_setup_board_command,
    looks_like_slack_board_followup,
)
from backend.routing.tool_plan_types import ToolPlan
from backend.routing.tool_plan_validator import validate_tool_plan
from backend.tools.registry import ToolRegistry


def test_extract_task_title_create_on_phrase():
    intent = "create a task on working on the revamping the AI as p0 and assign it to Amit"
    title = extract_task_title(intent)
    assert "revamping" in title.lower()
    assert "p0" not in title.lower()


def test_extract_task_title_strips_on_list_suffix():
    intent = "create task for net-new board smoke test on list F0BNP40SLV9"
    title = extract_task_title(intent)
    assert "net-new board smoke test" in title.lower()
    assert "f0bnp40slv9" not in title.lower()
    assert extract_list_id_override(intent) == "F0BNP40SLV9"


def test_placeholder_list_id_detection():
    assert is_placeholder_list_id("F0123ABCDEF")
    assert is_placeholder_list_id("F01234567")
    assert not is_placeholder_list_id("F0BNP40SLV9")


def test_direct_create_rejects_placeholder_binding_without_override(tmp_path: Path):
    from backend.db.slack_workflows_db import db_create_board_binding

    db_create_board_binding(
        tmp_path,
        board_key="bugs-tracker",
        list_id="F0123ABCDEF",
        channel_id="Ctech",
    )
    config = AlfredConfig(slack=SlackConfig(enabled=True, bot_token="xoxb-test"))
    task = Task(
        source="slack",
        user_id="U1",
        channel_id="Ctech",
        raw_text="create task for smoke test",
        cleaned_intent="create task for smoke test",
    )
    response, _meta = try_slack_board_create_direct(task, config, tmp_path)
    assert response is not None
    text = response.payload.data.get("text") or ""
    assert "placeholder" in text.lower()
    assert "F0123ABCDEF" in text


def test_direct_create_skips_when_channel_persona_prefers_jira(tmp_path: Path):
    from backend.db.slack_workflows_db import db_create_board_binding
    from backend.models.config import JiraConfig

    db_create_board_binding(
        tmp_path,
        board_key="team-tech",
        list_id="F0BQ0MH2LMB",
        channel_id="Ctech",
        persona_prompt="Primary: jira_create_issue with project=`TECH`.",
    )
    config = AlfredConfig(
        slack=SlackConfig(enabled=True, bot_token="xoxb-test"),
        jira=JiraConfig(enabled=True, default_project="TECH"),
    )
    task = Task(
        source="slack",
        user_id="U1",
        channel_id="Ctech",
        raw_text="create a task to have variant based PPCOD selection",
        cleaned_intent="create a task to have variant based PPCOD selection",
    )
    response, meta = try_slack_board_create_direct(task, config, tmp_path)
    assert response is None
    assert meta == {}


def test_direct_create_uses_list_override_and_updates_binding(tmp_path: Path):
    from backend.db.slack_workflows_db import db_create_board_binding, db_get_board_binding_for_channel

    db_create_board_binding(
        tmp_path,
        board_key="bugs-tracker",
        list_id="F0123ABCDEF",
        channel_id="Ctech",
    )
    config = AlfredConfig(slack=SlackConfig(enabled=True, bot_token="xoxb-test"))
    task = Task(
        source="slack",
        user_id="U1",
        channel_id="Ctech",
        thread_ts="1.1",
        raw_text="create task for smoke test on list F0REAL01",
        cleaned_intent="create task for smoke test on list F0REAL01",
    )
    fake = {
        "record_id": "Rec1",
        "display_id": "TS-9",
        "title": "smoke test",
        "status": "Not picked",
        "board": "bugs-tracker",
    }
    with patch(
        "backend.integrations.slack.lists_client.verify_list_id",
        return_value=(True, ""),
    ), patch(
        "backend.routing.slack_board.direct.create_board_task",
        return_value=fake,
    ) as create_mock:
        response, meta = try_slack_board_create_direct(task, config, tmp_path)
    assert response is not None
    binding = db_get_board_binding_for_channel(tmp_path, "Ctech")
    assert binding is not None
    assert binding["list_id"] == "F0REAL01"
    create_mock.assert_called_once()
    board_arg = create_mock.call_args.args[3]
    assert board_arg.list_id == "F0REAL01"
    assert meta["last_board_task"]["display_id"] == "TS-9"


def test_extract_board_create_fields_severity_and_title():
    task = Task(
        source="slack",
        user_id="U1",
        channel_id="C1",
        raw_text="create a task on revamping the AI as p0 and assign <@U2>",
        cleaned_intent="create a task on revamping the AI as p0 and assign it to someone",
    )
    fields = extract_board_create_fields(task)
    assert "revamping" in fields["title"].lower()
    assert fields["severity"] == "High"
    assert fields["assignee_user_id"] == "U2"


def test_extract_board_create_fields_assign_to_me():
    task = Task(
        source="slack",
        user_id="U_HUMAN",
        channel_id="C1",
        raw_text="<@UBOT> create a task for testing checkout and assign it to me",
        cleaned_intent="create a task for testing checkout and assign it to me",
    )
    fields = extract_board_create_fields(task, bot_user_id="UBOT")
    assert "testing checkout" in fields["title"].lower()
    assert fields["assignee_user_id"] == "U_HUMAN"


def test_create_task_with_board_in_title_is_not_setup_command():
    intent = "create task for net-new board smoke test"
    assert looks_like_setup_board_command(intent) is False


def test_followup_detects_is_it_created():
    assert looks_like_slack_board_followup(
        "yes is it created?",
        session_turns=(
            "create a task on revamping the AI as p0",
            "I'll create that task using Slack board management",
        ),
    )


def test_direct_create_returns_task(tmp_path: Path):
    from backend.db.slack_workflows_db import db_create_board_binding

    db_create_board_binding(
        tmp_path,
        board_key="bugs-tracker",
        list_id="Fbugs001",
        channel_id="Ctech",
    )
    config = AlfredConfig(
        slack=SlackConfig(
            enabled=True,
            bot_token="xoxb-test",
            board_workflows=SlackBoardWorkflowsConfig(
                enabled=True,
                boards=[
                    SlackBoardProfile(
                        name="bugs-tracker",
                        list_id="Fbugs001",
                        channel_ids=["Ctech"],
                        columns=SlackBoardColumnMap(),
                    )
                ],
            ),
        )
    )
    task = Task(
        source="slack",
        user_id="U1",
        channel_id="Ctech",
        thread_ts="1.1",
        raw_text="create a task on revamping the AI as p0",
        cleaned_intent="create a task on revamping the AI as p0",
    )
    fake = {
        "record_id": "Rec1",
        "display_id": "TS-9",
        "title": "revamping the AI",
        "status": "Not picked",
        "board": "bugs-tracker",
    }
    with patch(
        "backend.routing.slack_board.direct.create_board_task",
        return_value=fake,
    ) as create_mock:
        response, meta = try_slack_board_create_direct(task, config, tmp_path)
    assert response is not None
    text = response.payload.data.get("text") or ""
    assert "TS-9" in text
    assert meta["last_board_task"]["display_id"] == "TS-9"
    create_mock.assert_called_once()


def test_status_followup_uses_session_metadata():
    session = MagicMock()
    session.metadata = {
        "last_board_task": {
            "display_id": "TS-9",
            "title": "revamping the AI",
            "status": "Not picked",
            "list_id": "Fbugs001",
            "list_name": "bugs-tracker Tasks",
            "open_url": "https://app.slack.com/client/T1/Fbugs001",
        }
    }
    task = Task(
        source="slack",
        user_id="U1",
        channel_id="C1",
        raw_text="yes is it created?",
        cleaned_intent="yes is it created?",
    )
    response = try_slack_board_status_followup(
        task,
        AlfredConfig(slack=SlackConfig(enabled=True)),
        Path("."),
        session=session,
        session_turns=("create a task on revamping the AI",),
    )
    assert response is not None
    text = response.payload.data.get("text") or ""
    assert "TS-9" in text
    assert "Fbugs001" in text


def test_where_task_uses_latest_session_metadata():
    session = MagicMock()
    session.metadata = {
        "last_board_task": {
            "display_id": "TS-2",
            "record_id": "Rec2",
            "title": "testing checkout",
            "status": "Not picked",
            "list_id": "F0LIST",
            "list_name": "tmp-01 Tasks",
            "open_url": "https://app.slack.com/client/T1/F0LIST",
        }
    }
    task = Task(
        source="slack",
        user_id="U1",
        channel_id="C1",
        raw_text="where is task created?",
        cleaned_intent="where is task created?",
    )
    with patch(
        "backend.integrations.slack.lists_client.get_item",
        return_value={"id": "Rec2"},
    ):
        response = try_slack_board_where_direct(
            task,
            AlfredConfig(slack=SlackConfig(enabled=True, bot_token="xoxb-test")),
            Path("."),
            session=session,
        )
    assert response is not None
    text = response.payload.data.get("text") or ""
    assert "TS-2" in text
    assert "tmp-01 Tasks" in text
    assert "F0LIST" in text
    assert "TS-1" not in text


def test_direct_update_status(tmp_path: Path):
    from backend.db.slack_board_store import SlackBoardStore
    from backend.db.slack_workflows_db import db_create_board_binding

    db_create_board_binding(
        tmp_path,
        board_key="bugs-tracker",
        list_id="Fbugs001",
        channel_id="Ctech",
    )
    store = SlackBoardStore(tmp_path)
    store.register_record(
        "Rec1",
        board_key="bugs-tracker",
        list_id="Fbugs001",
        channel_id="Ctech",
        display_id="TS-3",
        title="Smoke test",
    )
    config = AlfredConfig(slack=SlackConfig(enabled=True, bot_token="xoxb-test"))
    task = Task(
        source="slack",
        user_id="U1",
        channel_id="Ctech",
        raw_text="@alfred move TS-3 to in progress",
        cleaned_intent="move TS-3 to in progress",
    )
    fake = {
        "record_id": "Rec1",
        "list_id": "Fbugs001",
        "updated": {"status": "In progress"},
    }
    with patch(
        "backend.routing.slack_board.direct.update_board_task",
        return_value=fake,
    ) as update_mock:
        response, meta = try_slack_board_update_direct(task, config, tmp_path)
    assert response is not None
    text = response.payload.data.get("text") or ""
    assert "In progress" in text
    update_mock.assert_called_once()
    assert update_mock.call_args.kwargs["status"] == "In progress"


def test_direct_update_st_prefix_inline_status(tmp_path: Path):
    from backend.db.slack_board_store import SlackBoardStore
    from backend.db.slack_workflows_db import db_create_board_binding

    db_create_board_binding(
        tmp_path,
        board_key="sales-tracker",
        list_id="Fbugs001",
        channel_id="Ctech",
        display_id_prefix="ST",
    )
    config = AlfredConfig(slack=SlackConfig(enabled=True, bot_token="xoxb-test"))
    task = Task(
        source="slack",
        user_id="U1",
        channel_id="Ctech",
        raw_text="@alfred ST-1 is in progress and assign severity to High. Also assign it to <@U2>",
        cleaned_intent="ST-1 is in progress and assign severity to High. Also assign it to user",
    )
    fake = {
        "record_id": "Rec1",
        "list_id": "Fbugs001",
        "updated": {
            "status": "In progress",
            "severity": "High",
            "assignee_user_id": "U2",
        },
    }
    with patch(
        "backend.routing.slack_board.direct.update_board_task",
        return_value=fake,
    ) as update_mock:
        response, _meta = try_slack_board_update_direct(task, config, tmp_path)
    assert response is not None
    update_mock.assert_called_once()
    assert update_mock.call_args.kwargs["ticket_ref"] == "ST-1"


def test_update_resolves_display_id_from_list_scan(tmp_path: Path):
    from backend.db.slack_workflows_db import db_create_board_binding
    from backend.domains.slack_board.operations import update_board_task

    db_create_board_binding(
        tmp_path,
        board_key="sales-tracker",
        list_id="Fbugs001",
        channel_id="Ctech",
        display_id_prefix="ST",
        columns={"display_id": "Display ID"},
    )
    config = AlfredConfig(
        slack=SlackConfig(enabled=True, bot_token="xoxb-test"),
    )
    client = MagicMock()
    schema = [
        {"id": "ColName", "name": "Name", "type": "text"},
        {"id": "ColDisplay", "name": "Display ID", "type": "text"},
        {"id": "ColStatus", "name": "Status", "type": "select",
         "options": {"choices": [{"value": "in_progress", "label": "In progress"}]}},
    ]
    list_item = {
        "id": "Rec1",
        "fields": [
            {"column_id": "ColName", "key": "name", "text": "Increasing sales"},
            {"column_id": "ColDisplay", "key": "display_id", "text": "ST-1"},
        ],
    }
    with patch(
        "backend.domains.slack_board.operations.load_schema",
        return_value=schema,
    ), patch(
        "backend.domains.slack_board.operations.list_items",
        return_value=[list_item],
    ), patch(
        "backend.domains.slack_board.operations.update_cells",
        return_value={"ok": True},
    ) as update_cells_mock, patch(
        "backend.domains.slack_board.operations.grant_list_access",
        return_value=[],
    ):
        from backend.db.slack_board_store import SlackBoardStore

        store = SlackBoardStore(tmp_path)
        result = update_board_task(
            client,
            config,
            store,
            ticket_ref="ST-1",
            status="In progress",
            channel_id="Ctech",
        )
    assert result["record_id"] == "Rec1"
    update_cells_mock.assert_called_once()
    assert store.resolve_record("ST-1") is not None


def test_direct_assign_uses_session_task_ref(tmp_path: Path):
    from backend.db.slack_workflows_db import db_create_board_binding

    db_create_board_binding(
        tmp_path,
        board_key="bugs-tracker",
        list_id="Fbugs001",
        channel_id="Ctech",
    )
    config = AlfredConfig(slack=SlackConfig(enabled=True, bot_token="xoxb-test"))
    task = Task(
        source="slack",
        user_id="U1",
        channel_id="Ctech",
        raw_text="@alfred assign this task to <@U2>",
        cleaned_intent="assign this task to user",
    )
    session = MagicMock()
    session.metadata = {
        "last_board_task": {
            "display_id": "TS-9",
            "record_id": "Rec1",
            "title": "Smoke",
            "status": "Not picked",
        }
    }
    fields = extract_board_update_fields(task, session_metadata=session.metadata)
    assert fields["ticket_ref"] == "TS-9"
    assert fields["assignee_user_id"] == "U2"
    fake = {
        "record_id": "Rec1",
        "updated": {"assignee_user_id": "U2"},
    }
    with patch(
        "backend.routing.slack_board.direct.update_board_task",
        return_value=fake,
    ) as update_mock:
        response, _meta = try_slack_board_update_direct(
            task, config, tmp_path, session=session
        )
    assert response is not None
    update_mock.assert_called_once()
    assert update_mock.call_args.kwargs["ticket_ref"] == "TS-9"
    assert update_mock.call_args.kwargs["assignee_user_id"] == "U2"


def test_direct_create_title_followup(tmp_path: Path):
    from backend.db.slack_workflows_db import db_create_board_binding

    db_create_board_binding(
        tmp_path,
        board_key="sales-tracker",
        list_id="Fbugs001",
        channel_id="Ctech",
    )
    config = AlfredConfig(slack=SlackConfig(enabled=True, bot_token="xoxb-test"))
    session = MagicMock()
    session.metadata = {"pending_board_create": True}
    task = Task(
        source="slack",
        user_id="U1",
        channel_id="Ctech",
        raw_text="Talk to CottonThreads",
        cleaned_intent="Talk to CottonThreads",
    )
    fake = {
        "record_id": "Rec1",
        "display_id": "ST-3",
        "title": "Talk to CottonThreads",
        "status": "Not picked",
        "board": "sales-tracker",
        "list_id": "Fbugs001",
    }
    with patch(
        "backend.routing.slack_board.direct.create_board_task",
        return_value=fake,
    ) as create_mock:
        response, meta = try_slack_board_create_direct(
            task,
            config,
            tmp_path,
            session=session,
            session_turns=("What should the task be called?",),
        )
    assert response is not None
    text = response.payload.data.get("text") or ""
    assert "Task created on your board" in text
    assert "ST-3" in text
    assert meta.get("pending_board_create") is False
    create_mock.assert_called_once()
    assert create_mock.call_args.kwargs["title"] == "Talk to CottonThreads"


def test_direct_create_batch_from_numbered_list(tmp_path: Path):
    from backend.db.slack_workflows_db import db_create_board_binding

    db_create_board_binding(
        tmp_path,
        board_key="bugs-tracker",
        list_id="Fbugs001",
        channel_id="Ctech",
    )
    config = AlfredConfig(slack=SlackConfig(enabled=True, bot_token="xoxb-test"))
    raw = "\n".join(
        [
            "1. Exit reason to be given on Export file",
            "2. Limit discount on cart - Everaw requirement",
            "3. Disable Partial COD on Coupons - Everaw requirement",
            "4. Multiple customers are being created - Everaw requirement",
            "5. UPI Intent - Mishmash and Everaw requirement",
            "6. Redirection Updates",
            "7. Add Freebie using coupon - AuraByNoureya",
            "8. Snapchat Integration",
            "@alfred create a task for all the above issues",
        ]
    )
    task = Task(
        source="slack",
        user_id="U1",
        channel_id="Ctech",
        raw_text=raw,
        cleaned_intent="create a task for all the above issues",
    )
    created = []
    captured_kwargs = []

    def _fake_create(*_args, **kwargs):
        captured_kwargs.append(kwargs)
        idx = len(created) + 1
        row = {
            "record_id": f"Rec{idx}",
            "display_id": f"TS-{idx}",
            "title": kwargs["title"],
            "status": "Not picked",
            "board": "bugs-tracker",
            "list_id": "Fbugs001",
        }
        created.append(row)
        return row

    from backend.routing.slack_board.task_draft import BoardTaskDraft

    def _fake_draft(**kwargs):
        return [
            BoardTaskDraft(
                title=title,
                description=(
                    f"Summary: {title}\n"
                    "Slack thread: https://slack.example/thread\n"
                    f"Context:\n• Work item: {title}\n"
                    "Requested by: @Azeem"
                ),
                severity="Medium",
            )
            for title in kwargs["item_titles"]
        ]

    with patch(
        "backend.routing.slack_board.direct.create_board_task",
        side_effect=_fake_create,
    ) as create_mock, patch(
        "backend.routing.slack_board.task_draft.draft_board_tasks_batch_from_thread",
        side_effect=_fake_draft,
    ):
        response, meta = try_slack_board_create_direct(task, config, tmp_path)
    assert response is not None
    text = response.payload.data.get("text") or ""
    assert "8 tasks created" in text
    assert "Snapchat Integration" in text
    assert create_mock.call_count == 8
    assert [row["title"] for row in created][0] == "Exit reason to be given on Export file"
    assert meta.get("pending_board_creates") == []
    assert "Summary: Snapchat Integration" in captured_kwargs[-1]["description"]
    assert "Exit reason" not in captured_kwargs[-1]["description"]
    assert "Summary: Exit reason to be given on Export file" in captured_kwargs[0]["description"]


def test_direct_create_batch_ignores_thread_bot_metadata(tmp_path: Path):
    from backend.db.slack_workflows_db import db_create_board_binding

    db_create_board_binding(
        tmp_path,
        board_key="bugs-tracker",
        list_id="Fbugs001",
        channel_id="Ctech",
    )
    config = AlfredConfig(slack=SlackConfig(enabled=True, bot_token="xoxb-test"))
    raw = "\n".join(
        [
            "can you create all the following tasks, each item is separate task",
            "• Exit reason to be given on Export file",
            "• Limit discount on cart - Everaw requirement",
            "• Disable Partial COD on Coupons - Everaw requirement",
            "• Multiple customers are being created - Everaw requirement",
            "• UPI Intent - Mishmash and Everaw requirement",
            "• Redirection Updates",
            "• Add Freebie using coupon - AuraByNoureya",
            "• Snapchat Integration",
        ]
    )
    task = Task(
        source="slack",
        user_id="U1",
        channel_id="Ctech",
        thread_ts="1.1",
        raw_text=raw,
        cleaned_intent="can you create all the following tasks, each item is separate task",
    )
    created = []

    def _fake_create(*_args, **kwargs):
        idx = len(created) + 1
        row = {
            "record_id": f"Rec{idx}",
            "display_id": f"TS-{idx}",
            "title": kwargs["title"],
            "status": "Not picked",
            "board": "bugs-tracker",
            "list_id": "Fbugs001",
        }
        created.append(row)
        return row

    from backend.routing.slack_board.task_draft import BoardTaskDraft

    def _fake_draft(**kwargs):
        return [
            BoardTaskDraft(title=title, description=f"Summary: {title}", severity="Medium")
            for title in kwargs["item_titles"]
        ]

    thread_messages = [
        {
            "user": "U1",
            "text": (
                "1. Exit reason to be given on Export file\n"
                "2. Limit discount on cart - Everaw requirement"
            ),
        },
        {
            "bot_id": "B1",
            "username": "alfred",
            "user": "UBOT",
            "text": (
                "Governance: `slack_board_create_task` requires explicit approval before I can run it.\n"
                "Planned action: create Slack List tasks"
            ),
        },
        {
            "bot_id": "B1",
            "username": "alfred",
            "user": "UBOT",
            "text": (
                "**Task created on your board** — **TS-4** · *Earlier item*\n"
                "- List: **team-tech Tasks** (`FOBQOMH2LMB`)\n"
                "- Status: `Not picked`\n"
                "- Severity: `Medium`\n"
                "- Assignee: `<@UAZEEM>`\n"
                "- Record: `Rec0BR4D3N205`\n"
                "- Open List: https://app.slack.com/client/T1/C1"
            ),
        },
        {
            "bot_id": "B1",
            "username": "alfred",
            "user": "UBOT",
            "text": "Governance: `jira_create_issue` requires explicit approval before I can run it.",
        },
        {"user": "U1", "text": raw},
    ]

    with patch(
        "backend.routing.slack_board.direct.create_board_task",
        side_effect=_fake_create,
    ) as create_mock, patch(
        "backend.routing.slack_board.task_draft.draft_board_tasks_batch_from_thread",
        side_effect=_fake_draft,
    ), patch(
        "backend.integrations.slack.context.fetch_thread_messages",
        return_value=thread_messages,
    ), patch(
        "backend.routing.slack_board.bootstrap._bot_user_id",
        return_value="UBOT",
    ):
        response, _meta = try_slack_board_create_direct(task, config, tmp_path)

    assert response is not None
    text = response.payload.data.get("text") or ""
    assert "8 tasks created" in text
    assert create_mock.call_count == 8
    titles = [row["title"] for row in created]
    assert titles[0] == "Exit reason to be given on Export file"
    assert titles[-1] == "Snapchat Integration"
    joined = " ".join(titles).lower()
    assert "governance" not in joined
    assert "assignee" not in joined
    assert "rec0br4d3n205" not in joined
    assert "jira_create_issue" not in joined


def test_direct_create_pending_batch_on_yes_proceed(tmp_path: Path):
    from backend.db.slack_workflows_db import db_create_board_binding
    from backend.models.config import GovernanceConfig

    db_create_board_binding(
        tmp_path,
        board_key="bugs-tracker",
        list_id="Fbugs001",
        channel_id="Ctech",
    )
    config = AlfredConfig(
        slack=SlackConfig(enabled=True, bot_token="xoxb-test"),
        governance=GovernanceConfig(enabled=True, require_confirmation=True),
    )
    session = MagicMock()
    session.metadata = {
        "pending_board_creates": [
            {"title": "Exit reason to be given on Export file"},
            {"title": "Snapchat Integration"},
        ]
    }
    task = Task(
        source="slack",
        user_id="U1",
        channel_id="Ctech",
        raw_text="yes, proceed",
        cleaned_intent="yes, proceed",
    )
    created = []

    def _fake_create(*_args, **kwargs):
        idx = len(created) + 1
        row = {
            "record_id": f"Rec{idx}",
            "display_id": f"TS-{idx}",
            "title": kwargs["title"],
            "status": "Not picked",
            "board": "bugs-tracker",
            "list_id": "Fbugs001",
        }
        created.append(row)
        return row

    from backend.routing.slack_board.task_draft import BoardTaskDraft

    with patch(
        "backend.routing.slack_board.direct.create_board_task",
        side_effect=_fake_create,
    ) as create_mock, patch(
        "backend.routing.slack_board.task_draft.draft_board_tasks_batch_from_thread",
        side_effect=lambda **kwargs: [
            BoardTaskDraft(title=title, description=f"Summary: {title}", severity="Medium")
            for title in kwargs["item_titles"]
        ],
    ):
        response, meta = try_slack_board_create_direct(
            task, config, tmp_path, session=session
        )
    assert response is not None
    assert create_mock.call_count == 2
    assert [row["title"] for row in created] == [
        "Exit reason to be given on Export file",
        "Snapchat Integration",
    ]
    assert meta.get("pending_board_creates") == []


def test_board_skill_keeps_full_tool_manifest():
    registry = ToolRegistry()
    for name in (
        "slack_fetch_thread",
        "slack_board_create_task",
        "slack_board_search_tasks",
    ):
        registry._tools[name] = MagicMock()
    plan = ToolPlan(
        goal="Check thread",
        confidence=0.8,
        tools_needed=["slack_fetch_thread"],
        intent_class="slack.board.search",
    )
    binding = validate_tool_plan(
        plan,
        registry,
        skill_allowed=[
            "slack_fetch_thread",
            "slack_board_create_task",
            "slack_board_search_tasks",
        ],
        skill_name="slack_board_management",
    )
    assert "slack_board_search_tasks" in binding.allowed_tools
    assert "slack_board_create_task" in binding.allowed_tools
