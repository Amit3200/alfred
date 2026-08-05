"""LangGraph task state for Alfred orchestration."""

from __future__ import annotations

from typing import Any, TypedDict


class AlfredGraphState(TypedDict, total=False):
    """Serializable graph state — runtime objects live in RunnableConfig."""

    task_id: str
    intent: str
    skill_name: str

    entities: dict[str, Any]
    tool_plan: dict[str, Any] | None
    scoped_tools: list[str]
    manifest_text: str
    goal_spec: dict[str, Any] | None

    route: str  # direct | worker | missing | done
    direct_handled: bool

    raw_reply: str
    response_kind: str  # text | structured | error
    response_data: dict[str, Any]
    metadata_patch: dict[str, Any] | None

    tool_trace: list[dict[str, Any]]
    grounding_passed: bool
    grounding_issues: list[str]

    error: str
