"""Validate and bind tool plans against registered tools."""

from __future__ import annotations

from backend.routing.tool_plan_types import ScopedToolBinding, ToolPlan
from backend.tools.catalog_formatter import format_tool_manifest
from backend.tools.registry import ToolRegistry

_SLACK_BOARD_SKILL = "slack_board_management"
_SLACK_BOARD_TOOLS = (
    "slack_fetch_thread",
    "slack_board_create_task",
    "slack_board_update_task",
    "slack_board_search_tasks",
    "slack_board_get_task",
    "slack_board_comment",
)


def validate_tool_plan(
    plan: ToolPlan | None,
    registry: ToolRegistry,
    *,
    skill_allowed: list[str] | None = None,
    skill_name: str | None = None,
) -> ScopedToolBinding:
    """Intersect plan tools with registry + skill allowlist."""
    registered = set(registry._tools.keys())

    if plan is None or not plan.tools_needed:
        allowed = list(skill_allowed or [])
        if allowed:
            allowed = [t for t in allowed if t in registered]
        else:
            allowed = sorted(registered)
        return ScopedToolBinding(
            plan=plan,
            allowed_tools=allowed,
            manifest_text=format_tool_manifest(allowed, registered_tools=registered),
            skill_name=skill_name,
        )

    validated: list[str] = []
    missing: list[str] = list(plan.missing_capabilities)

    for tool in plan.tools_needed:
        if tool not in registered:
            if tool not in missing:
                missing.append(tool)
            continue
        if skill_allowed and tool not in skill_allowed:
            continue
        validated.append(tool)

    if not validated and skill_allowed:
        validated = [t for t in skill_allowed if t in registered]

    if skill_name == _SLACK_BOARD_SKILL and skill_allowed:
        validated = [
            t
            for t in _SLACK_BOARD_TOOLS
            if t in skill_allowed and t in registered
        ] or validated

    if missing and plan:
        plan.missing_capabilities = missing

    return ScopedToolBinding(
        plan=plan,
        allowed_tools=validated,
        manifest_text=format_tool_manifest(validated, registered_tools=registered),
        skill_name=skill_name,
    )
