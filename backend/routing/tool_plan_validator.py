"""Validate and bind tool plans against registered tools."""

from __future__ import annotations

from backend.routing.tool_plan_types import ScopedToolBinding, ToolPlan
from backend.tools.catalog_formatter import format_tool_manifest
from backend.tools.registry import ToolRegistry

_SLACK_BOARD_SKILL = "slack_board_management"
_HTML_SLIDES_SKILL = "html_slides"
_SLACK_BOARD_TOOLS = (
    "slack_fetch_thread",
    "slack_board_create_task",
    "slack_board_update_task",
    "slack_board_search_tasks",
    "slack_board_get_task",
    "slack_board_comment",
)


def _manifest_for_skill(
    skill_name: str | None,
    allowed: list[str],
    registered: set[str],
    *,
    publish_requested: bool = False,
    saved_filename: str = "",
) -> str:
    manifest = format_tool_manifest(allowed, registered_tools=registered)
    if skill_name == _HTML_SLIDES_SKILL:
        from backend.routing.html_slides_delivery import html_slides_tool_manifest_addendum

        manifest = f"{manifest}{html_slides_tool_manifest_addendum(
            publish_requested=publish_requested,
            saved_filename=saved_filename,
        )}"
    return manifest


def _html_slides_allowed_tools(skill_allowed: list[str] | None, registered: set[str]) -> list[str]:
    from backend.routing.html_slides_delivery import ARTIFACT_TOOLS

    if not skill_allowed:
        return sorted(t for t in ARTIFACT_TOOLS if t in registered)
    return [t for t in skill_allowed if t in registered and t in ARTIFACT_TOOLS]


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
        if skill_name == _HTML_SLIDES_SKILL:
            allowed = _html_slides_allowed_tools(skill_allowed, registered) or allowed
        if allowed:
            allowed = [t for t in allowed if t in registered]
        else:
            allowed = sorted(registered)
        return ScopedToolBinding(
            plan=plan,
            allowed_tools=allowed,
            manifest_text=_manifest_for_skill(skill_name, allowed, registered),
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

    if skill_name == _HTML_SLIDES_SKILL:
        artifact_allowed = _html_slides_allowed_tools(skill_allowed, registered)
        if artifact_allowed:
            validated = artifact_allowed
        if missing and plan:
            plan.missing_capabilities = missing
        publish_requested = "publish_html_artifact" in (plan.tools_needed if plan else [])
        return ScopedToolBinding(
            plan=plan,
            allowed_tools=validated,
            manifest_text=_manifest_for_skill(
                skill_name,
                validated,
                registered,
                publish_requested=publish_requested or "publish_html_artifact" in validated,
            ),
            skill_name=skill_name,
        )

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
        manifest_text=_manifest_for_skill(skill_name, validated, registered),
        skill_name=skill_name,
    )
