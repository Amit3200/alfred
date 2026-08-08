"""LangGraph route selection after tool plan validation."""

from __future__ import annotations

from typing import Any

from backend.routing.slack_board_agent import is_slack_board_write_intent


def resolve_graph_route(plan: Any | None, *, allowed_tools: list[str]) -> str:
    """Choose LangGraph branch: missing_tools, try_direct, or run_worker."""
    if plan and getattr(plan, "missing_capabilities", None) and not allowed_tools:
        return "missing"
    intent_class = getattr(plan, "intent_class", "") if plan else ""
    if intent_class == "repo.docs.qa" or is_slack_board_write_intent(intent_class):
        return "worker"
    if plan and len(getattr(plan, "steps", None) or []) == 1:
        return "direct"
    return "worker"
