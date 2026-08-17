"""LangGraph route selection after tool plan validation."""

from __future__ import annotations

from typing import Any

from backend.routing.classifier.intent_classes import is_html_slides_intent
from backend.routing.slack_board.agent import is_slack_board_write_intent


def resolve_graph_route(plan: Any | None, *, allowed_tools: list[str]) -> str:
    """Choose LangGraph branch: missing_tools, try_direct, or run_worker."""
    if plan and getattr(plan, "missing_capabilities", None) and not allowed_tools:
        return "missing"
    intent_class = getattr(plan, "intent_class", "") if plan else ""
    if is_html_slides_intent(intent_class):
        if plan and len(getattr(plan, "steps", None) or []) == 1:
            from backend.routing.html_slides_delivery import publish_args_complete

            step = plan.steps[0]
            if getattr(step, "tool", "") == "publish_html_artifact" and publish_args_complete(
                dict(step.args_hint or {})
            ):
                return "direct"
        return "worker"
    if intent_class in ("repo.docs.qa",) or is_slack_board_write_intent(intent_class):
        return "worker"
    if plan and len(getattr(plan, "steps", None) or []) == 1:
        step = plan.steps[0]
        if getattr(step, "tool", "") == "save_html_deck":
            return "worker"
        return "direct"
    return "worker"
