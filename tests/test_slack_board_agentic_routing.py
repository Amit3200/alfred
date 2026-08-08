"""Tests for agentic Slack board routing and tool selection."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from backend.models.config import AlfredConfig, SlackConfig
from backend.models.task import Task
from backend.orchestrator.graph.plan_routing import resolve_graph_route
from backend.routing.slack_board_agent import (
    seed_slack_board_agent_plan,
    slack_board_agentic_addendum,
)
from backend.routing.tool_plan_types import ToolPlan, ToolPlanStep


def test_plan_routing_board_writes_use_worker():
    for intent in ("slack.board.create", "slack.board.update", "slack.board.comment"):
        plan = ToolPlan(
            goal="mutate board",
            confidence=0.9,
            tools_needed=["slack_board_update_task"],
            steps=[ToolPlanStep("slack_board_update_task", "update")],
            intent_class=intent,
        )
        assert resolve_graph_route(plan, allowed_tools=["slack_board_update_task"]) == "worker"


def test_plan_routing_board_search_can_use_direct():
    plan = ToolPlan(
        goal="search board",
        confidence=0.8,
        tools_needed=["slack_board_search_tasks"],
        steps=[ToolPlanStep("slack_board_search_tasks", "search")],
        intent_class="slack.board.search",
    )
    assert resolve_graph_route(plan, allowed_tools=["slack_board_search_tasks"]) == "direct"


def test_agentic_addendum_lists_read_and_write_tools():
    text = slack_board_agentic_addendum(intent_class="slack.board.update")
    assert "slack_board_create_task" in text
    assert "slack_board_update_task" in text
    assert "READ" in text
    assert "WRITE" in text


def test_seed_board_agent_plan_returns_metadata(tmp_path: Path):
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
        goal="Create Slack List task",
        confidence=0.88,
        tools_needed=["slack_board_create_task"],
        steps=[ToolPlanStep("slack_board_create_task", "create", {"title": "CottonThreads outreach"})],
        intent_class="slack.board.create",
        strategy="llm",
    )
    provider = MagicMock()
    with patch("backend.routing.tool_planner.resolve_tool_plan", return_value=plan):
        meta = seed_slack_board_agent_plan(task, config, tmp_path, provider=provider)
    assert meta.get("force_investigation_skill") == "slack_board_management"
    assert meta.get("board_agent_plan", {}).get("intent_class") == "slack.board.create"


def test_seed_board_agent_plan_skips_regex_matches(tmp_path: Path):
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
        meta = seed_slack_board_agent_plan(task, config, tmp_path, provider=provider)
    assert meta == {}
    plan_mock.assert_not_called()
