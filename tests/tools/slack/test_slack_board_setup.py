"""Tests for @alfred setup board and slackLists.create helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from backend.db.slack_workflows_db import db_get_board_binding_for_channel, db_get_channel_workflow
from backend.integrations.slack.board_keys import derive_list_name
from backend.integrations.slack.lists_client import (
    ALFRED_BOARD_COLUMN_MAP,
    alfred_board_list_schema,
    create_list,
    provision_alfred_board_list,
)
from backend.models.config import AlfredConfig, SlackConfig
from backend.models.task import Task
from backend.routing.slack_board.admin import try_slack_board_admin_command


def test_derive_list_name_from_channel():
    assert derive_list_name(channel_name="tmp-01") == "tmp-01 Tasks"
    assert derive_list_name(channel_id="C0BNNSMGG91") == "Board Nnsmgg91 Tasks"


def test_alfred_board_list_schema_includes_display_id():
    schema = alfred_board_list_schema()
    names = [col["name"] for col in schema]
    assert "Name" in names
    assert "Status" in names
    assert "Display ID" in names


def test_create_list_calls_slack_api():
    client = MagicMock()
    client.api_call.return_value = {
        "ok": True,
        "list_id": "F0NEWLIST",
        "list_metadata": {"schema": [{"id": "Col1", "name": "Name"}]},
    }
    result = create_list(client, name="tmp-01 Tasks")
    assert result["list_id"] == "F0NEWLIST"
    client.api_call.assert_called_once()
    args, kwargs = client.api_call.call_args
    assert args[0] == "slackLists.create"
    assert kwargs["json"]["name"] == "tmp-01 Tasks"
    assert kwargs["json"]["schema"]


@patch("backend.integrations.slack.lists_client.verify_list_id", return_value=(True, ""))
@patch("backend.integrations.slack.lists_client.list_open_url", return_value="https://app.slack.com/client/T1/F0NEWLIST")
@patch("backend.integrations.slack.lists_client.grant_list_access", return_value=[])
@patch("backend.integrations.slack.lists_client.create_list", return_value={"list_id": "F0NEWLIST"})
def test_provision_alfred_board_list(mock_create, mock_grant, mock_url, mock_verify):
    client = MagicMock()
    list_id, notes, open_url = provision_alfred_board_list(
        client,
        channel_id="C_TMP",
        list_name="tmp-01 Tasks",
        requesting_user_id="U1",
    )
    assert list_id == "F0NEWLIST"
    assert notes == []
    assert "F0NEWLIST" in open_url
    mock_create.assert_called_once()
    mock_grant.assert_called_once()
    mock_verify.assert_called_once()
    assert mock_grant.call_args.kwargs.get("requesting_user_id") == "U1"


@patch("backend.routing.slack_board.admin.fetch_slack_channel_name", return_value="tmp-01")
@patch(
    "backend.integrations.slack.lists_client.provision_alfred_board_list",
    return_value=("F0NEWLIST", [], "https://app.slack.com/client/T1/F0NEWLIST"),
)
def test_setup_board_creates_binding(mock_provision, mock_fetch, tmp_path):
    task = Task(
        source="slack",
        user_id="U1",
        channel_id="C_TMP",
        raw_text="@alfred setup board",
        cleaned_intent="setup board",
    )
    response = try_slack_board_admin_command(
        task,
        AlfredConfig(slack=SlackConfig(enabled=True, bot_token="xoxb-test")),
        tmp_path,
    )
    assert response is not None
    text = response.payload.data.get("text") or ""
    assert "F0NEWLIST" in text
    assert "app.slack.com" in text
    assert "create task" in text.lower()
    binding = db_get_board_binding_for_channel(tmp_path, "C_TMP")
    assert binding is not None
    assert binding["list_id"] == "F0NEWLIST"
    assert binding["columns"]["display_id"] == ALFRED_BOARD_COLUMN_MAP["display_id"]
    workflow = db_get_channel_workflow(tmp_path, "C_TMP")
    assert workflow is not None
    assert workflow["ticket_system"] == "slack_list"
    mock_provision.assert_called_once()


@patch(
    "backend.integrations.slack.lists_client.provision_alfred_board_list",
    side_effect=RuntimeError("missing_scope"),
)
def test_setup_board_surfaces_create_errors(mock_provision, tmp_path):
    task = Task(
        source="slack",
        user_id="U1",
        channel_id="C_TMP",
        raw_text="@alfred setup board",
        cleaned_intent="setup board",
    )
    response = try_slack_board_admin_command(
        task,
        AlfredConfig(slack=SlackConfig(enabled=True, bot_token="xoxb-test")),
        tmp_path,
    )
    assert response is not None
    text = response.payload.data.get("text") or ""
    assert "Could not create Slack List" in text
    assert db_get_board_binding_for_channel(tmp_path, "C_TMP") is None


def test_create_task_with_board_in_title_does_not_run_setup(tmp_path):
    task = Task(
        source="slack",
        user_id="U1",
        channel_id="C_TMP",
        raw_text="@alfred create task for net-new board smoke test",
        cleaned_intent="create task for net-new board smoke test",
    )
    response = try_slack_board_admin_command(
        task,
        AlfredConfig(slack=SlackConfig(enabled=True, bot_token="xoxb-test")),
        tmp_path,
    )
    assert response is None


def test_setup_board_skips_when_channel_already_linked(tmp_path):
    from backend.db.slack_workflows_db import db_create_board_binding

    db_create_board_binding(
        tmp_path,
        board_key="tmp-01",
        list_id="F0EXISTING",
        list_name="tmp-01 Tasks",
        channel_id="C_TMP",
    )
    task = Task(
        source="slack",
        user_id="U1",
        channel_id="C_TMP",
        raw_text="@alfred setup board",
        cleaned_intent="setup board",
    )
    with patch(
        "backend.integrations.slack.lists_client.provision_alfred_board_list",
    ) as mock_provision, patch(
        "backend.integrations.slack.lists_client.list_open_url",
        return_value="https://app.slack.com/client/T1/F0EXISTING",
    ):
        response = try_slack_board_admin_command(
            task,
            AlfredConfig(slack=SlackConfig(enabled=True, bot_token="xoxb-test")),
            tmp_path,
        )
    assert response is not None
    text = response.payload.data.get("text") or ""
    assert "already linked" in text.lower()
    assert "F0EXISTING" in text
    mock_provision.assert_not_called()


def test_share_board_grants_access(tmp_path):
    from backend.db.slack_workflows_db import db_create_board_binding

    db_create_board_binding(
        tmp_path,
        board_key="tmp-01",
        list_id="F0BNTMSSYH4",
        list_name="tmp-01 Tasks",
        channel_id="C_TMP",
    )
    task = Task(
        source="slack",
        user_id="U1",
        channel_id="C_TMP",
        raw_text="@alfred share board with <@U2|Amit>",
        cleaned_intent="share board with Amit",
    )
    with patch(
        "backend.integrations.slack.lists_client.share_list_with_users",
        return_value=[],
    ) as mock_share, patch(
        "backend.integrations.slack.lists_client.list_open_url",
        return_value="https://app.slack.com/client/T1/F0BNTMSSYH4",
    ):
        response = try_slack_board_admin_command(
            task,
            AlfredConfig(slack=SlackConfig(enabled=True, bot_token="xoxb-test")),
            tmp_path,
        )
    assert response is not None
    text = response.payload.data.get("text") or ""
    assert "Shared List" in text
    assert "F0BNTMSSYH4" in text
    mock_share.assert_called_once()
    assert mock_share.call_args.args[2] == ["U2"]


def test_tool_result_slack_messages_maps_to_text():
    from backend.orchestrator.processor import _tool_result_to_response
    from backend.tools.result import ToolResult

    response = _tool_result_to_response(
        ToolResult(kind="slack_messages", data={"text": "thread summary", "message_count": 3}),
    )
    assert response is not None
    assert response.payload.kind == "text"
    assert response.payload.data["text"] == "thread summary"
