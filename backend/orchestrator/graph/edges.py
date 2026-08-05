"""Conditional routing for Alfred LangGraph."""

from __future__ import annotations

from backend.orchestrator.graph.state import AlfredGraphState


def route_after_validate(state: AlfredGraphState) -> str:
    route = state.get("route") or "worker"
    if route == "missing":
        return "missing_tools"
    if route == "direct":
        return "try_direct"
    return "run_worker"


def route_after_direct(state: AlfredGraphState) -> str:
    if state.get("direct_handled"):
        return "format_reply"
    return "run_worker"
