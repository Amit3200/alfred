"""Shared helpers for agentic Slack List board tool selection."""

from __future__ import annotations

from typing import Any

from backend.ai.base import LLMProvider
from backend.models.config import AlfredConfig
from backend.models.task import Task
from backend.routing.tool_plan_types import ToolPlan
from backend.routing.types import RouteContext
from backend.tools.catalog import SLACK_BOARD_READ_TOOLS, SLACK_BOARD_WRITE_TOOLS

SLACK_BOARD_WRITE_INTENTS = frozenset(
    {
        "slack.board.create",
        "slack.board.update",
        "slack.board.comment",
        "slack.board.write.create",
        "slack.board.write.update",
        "slack.board.write.comment",
    }
)

SLACK_BOARD_PLANNER_TOOLS = tuple(
    sorted(SLACK_BOARD_WRITE_TOOLS | SLACK_BOARD_READ_TOOLS)
)


def is_slack_board_write_intent(intent_class: str) -> bool:
    return (intent_class or "").strip() in SLACK_BOARD_WRITE_INTENTS


def slack_board_agentic_addendum(*, intent_class: str = "") -> str:
    intent = (intent_class or "slack.board").strip()
    return (
        "\n\n## Slack List board — agentic tool selection\n"
        "You have **READ** tools (`slack_fetch_thread`, `slack_board_search_tasks`, "
        "`slack_board_get_task`) and **WRITE** tools (`slack_board_create_task`, "
        "`slack_board_update_task`, `slack_board_comment`).\n\n"
        "**Workflow:**\n"
        "1. Reason about whether the user wants create, update (status/assignee/severity), "
        "comment, or read-only lookup.\n"
        "2. Use READ tools when the task id, title, or thread context is unclear.\n"
        "3. Call the matching WRITE tool for any mutation — never claim create/update/assign "
        "in prose without a successful write tool in your trace.\n\n"
        f"**Planner intent:** `{intent}` — pick the write tool that matches it.\n"
        "Review the tool manifest below before your first tool call."
    )


def seeded_board_agent_plan(session: Any | None) -> ToolPlan | None:
    if session is None:
        return None
    raw = dict(getattr(session, "metadata", None) or {}).get("board_agent_plan")
    if not raw:
        return None
    from backend.orchestrator.graph.serialize import tool_plan_from_dict

    return tool_plan_from_dict(raw)


def clear_board_agent_plan_seed(session: Any | None) -> None:
    if session is None:
        return
    meta = dict(getattr(session, "metadata", None) or {})
    meta.pop("board_agent_plan", None)
    meta.pop("force_investigation_skill", None)
    session.metadata = meta


def seed_slack_board_agent_plan(
    task: Task,
    config: AlfredConfig,
    data_dir: Any,
    *,
    session: Any | None = None,
    session_turns: tuple[str, ...] = (),
    provider: LLMProvider | None = None,
    model: str | None = None,
    min_confidence: float | None = None,
) -> dict[str, Any]:
    """Plan ambiguous board messages via LLM and seed the agent investigation path."""
    if task.source != "slack" or not config.slack.enabled:
        return {}
    if not config.routing.tool_planner_enabled or provider is None:
        return {}

    from backend.domains.slack_board.operations import board_enabled, resolve_board_for_task
    from backend.routing.slack_board.intent import (
        looks_like_slack_board_create,
        looks_like_slack_board_update,
    )
    from backend.routing.tool_planner import planner_llm_enabled, resolve_tool_plan

    if not board_enabled(config, data_dir) or not resolve_board_for_task(
        config, task, data_dir=data_dir
    ):
        return {}

    intent = task.cleaned_intent or task.raw_text or ""
    if looks_like_slack_board_create(intent) or looks_like_slack_board_update(intent):
        return {}

    if not planner_llm_enabled(config):
        return {}

    session_meta = dict((session.metadata if session else {}) or {})
    context = RouteContext(
        intent=intent,
        channel_id=task.channel_id or "",
        session_turns=session_turns,
    )
    threshold = (
        min_confidence
        if min_confidence is not None
        else config.routing.tool_planner_min_confidence
    )
    plan = resolve_tool_plan(
        config,
        task,
        context,
        provider=provider,
        model=model,
        skill_allowed=list(SLACK_BOARD_PLANNER_TOOLS),
        data_dir=data_dir,
        session_metadata=session_meta,
    )
    if not plan or plan.confidence < threshold:
        return {}

    intent_class = (plan.intent_class or "").strip()
    if intent_class not in SLACK_BOARD_WRITE_INTENTS:
        return {}

    write_tools = [t for t in plan.tools_needed if t in SLACK_BOARD_WRITE_TOOLS]
    if not write_tools:
        return {}

    from backend.orchestrator.graph.serialize import tool_plan_to_dict

    return {
        "board_agent_plan": tool_plan_to_dict(plan),
        "force_investigation_skill": "slack_board_management",
    }
