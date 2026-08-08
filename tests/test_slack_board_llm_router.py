"""Tests for LLM-assisted Slack board routing."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from backend.models.config import AlfredConfig, SlackConfig
from backend.models.task import Task
from backend.routing.slack_board_llm_router import try_slack_board_llm_direct
from backend.routing.tool_plan_types import ToolPlan, ToolPlanStep
from backend.routing.tool_planner import _format_planner_session_context


def test_planner_session_context_includes_last_task():
    context = _format_planner_session_context(
        {
            "pending_board_create": True,
            "last_board_task": {
                "display_id": "ST-2",
                "title": "Talk to CottonThreads",
                "record_id": "RecABC",
            },
        }
    )
    assert "awaiting task title" in context
    assert "ST-2" in context
    assert "Talk to CottonThreads" in context


def test_llm_router_create_when_regex_misses(tmp_path: Path):
    from backend.db.slack_workflows_db import db_create_board_binding

    db_create_board_binding(
        tmp_path,
        board_key="sales-tracker",
        list_id="Fbugs001",
        channel_id="Ctech",
    )
    config = AlfredConfig(slack=SlackConfig(enabled=True, bot_token="xoxb-test"))
    task = Task(
        source="slack",
        user_id="U1",
        channel_id="Ctech",
        raw_text="please log CottonThreads outreach on the board",
        cleaned_intent="please log CottonThreads outreach on the board",
    )
    plan = ToolPlan(
        goal="Create Slack List task for CottonThreads outreach",
        confidence=0.88,
        tools_needed=["slack_board_create_task"],
        steps=[
            ToolPlanStep(
                "slack_board_create_task",
                "create task",
                {"title": "CottonThreads outreach"},
            )
        ],
        intent_class="slack.board.create",
        strategy="llm",
    )
    fake = {
        "record_id": "Rec1",
        "display_id": "ST-4",
        "title": "CottonThreads outreach",
        "status": "Not picked",
        "board": "sales-tracker",
        "list_id": "Fbugs001",
    }
    provider = MagicMock()
    with patch(
        "backend.routing.tool_planner.resolve_tool_plan",
        return_value=plan,
    ), patch(
        "backend.routing.slack_board_direct.create_board_task",
        return_value=fake,
    ) as create_mock:
        response, meta = try_slack_board_llm_direct(
            task,
            config,
            tmp_path,
            provider=provider,
        )
    assert response is not None
    text = response.payload.data.get("text") or ""
    assert "Task created on your board" in text
    assert "ST-4" in text
    create_mock.assert_called_once()
    assert create_mock.call_args.kwargs["title"] == "CottonThreads outreach"
    assert meta.get("last_board_task", {}).get("display_id") == "ST-4"


def test_llm_router_skips_when_regex_already_matches(tmp_path: Path):
    from backend.db.slack_workflows_db import db_create_board_binding

    db_create_board_binding(
        tmp_path,
        board_key="sales-tracker",
        list_id="Fbugs001",
        channel_id="Ctech",
    )
    config = AlfredConfig(slack=SlackConfig(enabled=True, bot_token="xoxb-test"))
    task = Task(
        source="slack",
        user_id="U1",
        channel_id="Ctech",
        raw_text="create task for CottonThreads",
        cleaned_intent="create task for CottonThreads",
    )
    provider = MagicMock()
    with patch("backend.routing.tool_planner.resolve_tool_plan") as plan_mock:
        response, _meta = try_slack_board_llm_direct(
            task,
            config,
            tmp_path,
            provider=provider,
        )
    assert response is None
    plan_mock.assert_not_called()
