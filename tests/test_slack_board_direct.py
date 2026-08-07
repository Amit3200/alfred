"""Direct Slack board create and follow-up tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from backend.models.config import AlfredConfig, SlackBoardColumnMap, SlackBoardProfile, SlackBoardWorkflowsConfig, SlackConfig
from backend.models.task import Task
from backend.routing.slack_board_direct import (
    extract_board_create_fields,
    try_slack_board_create_direct,
    try_slack_board_status_followup,
)
from backend.routing.slack_board_intent import extract_task_title, looks_like_slack_board_followup
from backend.routing.tool_plan_types import ToolPlan
from backend.routing.tool_plan_validator import validate_tool_plan
from backend.tools.registry import ToolRegistry


def test_extract_task_title_create_on_phrase():
    intent = "create a task on working on the revamping the AI as p0 and assign it to Amit"
    title = extract_task_title(intent)
    assert "revamping" in title.lower()
    assert "p0" not in title.lower()


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
    assert fields["severity"] == "P0"
    assert fields["assignee_user_id"] == "U2"


def test_followup_detects_is_it_created():
    assert looks_like_slack_board_followup(
        "yes is it created?",
        session_turns=(
            "create a task on revamping the AI as p0",
            "I'll create that task using Slack board management",
        ),
    )


def test_direct_create_returns_task(tmp_path: Path):
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
        "backend.routing.slack_board_direct.create_board_task",
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
    assert "TS-9" in (response.payload.data.get("text") or "")


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
