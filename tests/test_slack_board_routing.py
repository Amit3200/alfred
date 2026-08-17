"""Tests for slack.board.create LangGraph routing."""

from __future__ import annotations

from backend.orchestrator.graph.plan_routing import resolve_graph_route
from backend.routing.tool_plan_types import ToolPlan, ToolPlanStep


def test_board_create_routes_to_worker():
    plan = ToolPlan(
        goal="Create board task",
        confidence=0.9,
        tools_needed=["slack_board_create_task"],
        steps=[ToolPlanStep("slack_board_create_task", "create")],
        intent_class="slack.board.create",
    )
    assert resolve_graph_route(plan, allowed_tools=["slack_board_create_task"]) == "worker"
