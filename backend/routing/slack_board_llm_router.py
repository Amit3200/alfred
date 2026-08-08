"""LLM-assisted routing for Slack List board ops when regex direct handlers miss."""

from __future__ import annotations

import logging
from typing import Any

from backend.ai.base import LLMProvider
from backend.models.config import AlfredConfig
from backend.models.response import AssistantResponse
from backend.models.task import Task
from backend.routing.tool_plan_types import ToolPlan
from backend.routing.types import RouteContext

logger = logging.getLogger(__name__)

_SLACK_BOARD_TOOLS = (
    "slack_board_create_task",
    "slack_board_update_task",
    "slack_board_search_tasks",
    "slack_fetch_thread",
)


def _title_from_plan(plan: ToolPlan) -> str:
    for step in plan.steps:
        if step.tool != "slack_board_create_task":
            continue
        hint = dict(step.args_hint or {})
        for key in ("title", "task_title", "name"):
            value = str(hint.get(key) or "").strip()
            if value:
                return value[:200]
    return ""


def _update_fields_from_plan(plan: ToolPlan) -> dict[str, str]:
    fields = {"ticket_ref": "", "status": "", "severity": "", "assignee_user_id": ""}
    for step in plan.steps:
        if step.tool != "slack_board_update_task":
            continue
        hint = dict(step.args_hint or {})
        for key in fields:
            value = str(hint.get(key) or hint.get(key.replace("_user_id", "")) or "").strip()
            if value:
                fields[key] = value
    return fields


def try_slack_board_llm_direct(
    task: Task,
    config: AlfredConfig,
    data_dir: Any,
    *,
    session: Any | None = None,
    session_turns: tuple[str, ...] = (),
    provider: LLMProvider | None = None,
    model: str | None = None,
    min_confidence: float | None = None,
) -> tuple[AssistantResponse | None, dict[str, Any]]:
    """Use the LLM tool planner to route ambiguous board messages to direct handlers."""
    if task.source != "slack" or not config.slack.enabled:
        return None, {}
    if not config.routing.tool_planner_enabled or provider is None:
        return None, {}

    from backend.integrations.slack.board_service import board_enabled, resolve_board_for_task
    from backend.routing.slack_board_intent import (
        looks_like_slack_board_create,
        looks_like_slack_board_update,
    )
    from backend.routing.tool_planner import planner_llm_enabled, resolve_tool_plan

    if not board_enabled(config, data_dir) or not resolve_board_for_task(
        config, task, data_dir=data_dir
    ):
        return None, {}

    intent = task.cleaned_intent or task.raw_text or ""
    if looks_like_slack_board_create(intent) or looks_like_slack_board_update(intent):
        return None, {}

    if not planner_llm_enabled(config):
        return None, {}

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
        skill_allowed=list(_SLACK_BOARD_TOOLS),
        data_dir=data_dir,
        session_metadata=session_meta,
    )
    if not plan or plan.confidence < threshold:
        return None, {}

    intent_class = (plan.intent_class or "").strip()
    if intent_class not in ("slack.board.create", "slack.board.update"):
        return None, {}

    from backend.routing.slack_board_direct import (
        try_slack_board_create_direct,
        try_slack_board_update_direct,
    )

    if intent_class == "slack.board.create":
        if "slack_board_create_task" not in plan.tools_needed:
            return None, {}
        logger.info(
            "LLM board router: create confidence=%.2f goal=%s",
            plan.confidence,
            plan.goal,
        )
        return try_slack_board_create_direct(
            task,
            config,
            data_dir,
            session=session,
            session_turns=session_turns,
            force_intent_class=intent_class,
            title_override=_title_from_plan(plan),
        )

    if "slack_board_update_task" not in plan.tools_needed:
        return None, {}
    logger.info(
        "LLM board router: update confidence=%.2f goal=%s",
        plan.confidence,
        plan.goal,
    )
    return try_slack_board_update_direct(
        task,
        config,
        data_dir,
        session=session,
        force_intent_class=intent_class,
        plan_fields=_update_fields_from_plan(plan),
    )
