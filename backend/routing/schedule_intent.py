"""Detect schedule-management intents so they are not stolen by slides or plan templates."""

from __future__ import annotations

import re
from typing import Any

from backend.models.task import Task
from backend.routing.tool_plan_types import ToolPlan, ToolPlanStep

_SCHEDULE_MANAGE_RE = re.compile(
    r"(?:"
    r"\bcreate\s+(?:a\s+)?schedule\b|"
    r"\bschedule\s+(?:a\s+|this\s+|the\s+)?(?:job|task|cron|playbook)\b|"
    r"\bschedule\s+(?:it|this)\b|"
    r"\blist\s+schedules?\b|"
    r"\b(?:delete|toggle|update|edit|disable|enable|activate|deactivate)\s+(?:the\s+)?schedule\b|"
    r"\bmanage\s+schedules?\b|"
    r"\bcron\s+(?:job|schedule|expression)\b|"
    r"\bevery\s+day\s+at\b"
    r")",
    re.I,
)

_CRON_FIELD = r"(?:\*(?:/\d+)?|\d{1,2}(?:-\d{1,2})?(?:/\d+)?(?:,\d{1,2}(?:-\d{1,2})?(?:/\d+)?)*)"
_CRON_DOW = rf"(?:{_CRON_FIELD}|[A-Za-z]{{3}}(?:-[A-Za-z]{{3}})?)"
_CRON_RE = re.compile(
    rf"(?<!\S)({_CRON_FIELD}\s+{_CRON_FIELD}\s+{_CRON_FIELD}\s+{_CRON_FIELD}\s+{_CRON_DOW})(?!\S)"
)
_SNAKE_NAME_RE = re.compile(r"\b([a-z][a-z0-9]*(?:_[a-z0-9]+)+)\b")
_TZ_RE = re.compile(r"\b(UTC|Asia/Kolkata|America/New_York|Europe/London|US/Pacific|US/Eastern)\b", re.I)


def looks_like_schedule_request(text: str) -> bool:
    """True when the user wants to create or manage a cron job, not run it now."""
    return bool(_SCHEDULE_MANAGE_RE.search(text or ""))


def extract_cron_expression(text: str) -> str:
    match = _CRON_RE.search(text or "")
    return match.group(1).strip() if match else ""


def extract_schedule_timezone(text: str) -> str:
    raw = text or ""
    match = _TZ_RE.search(raw)
    if match:
        token = match.group(1)
        if token.upper() == "UTC":
            return "UTC"
        return token
    if re.search(r"\bist\b", raw, re.I):
        return "Asia/Kolkata"
    return ""


def extract_schedule_name(text: str) -> str:
    for match in _SNAKE_NAME_RE.finditer((text or "").lower()):
        name = match.group(1)
        if name.startswith("job_"):
            continue
        return name
    return ""


def schedule_intent_class(text: str) -> str:
    """Canonical intent class for a schedule-management request."""
    return _schedule_action(text)[1]


def _schedule_action(text: str) -> tuple[str, str]:
    lower = (text or "").lower()
    if re.search(r"\blist\s+schedules?\b", lower):
        return "list_schedules", "schedule.read.list"
    if re.search(r"\bdelete\s+(?:the\s+)?schedule\b", lower):
        return "delete_schedule", "schedule.write.delete"
    if re.search(r"\b(?:toggle|disable|enable|activate|deactivate)\s+(?:the\s+)?schedule\b", lower):
        return "toggle_schedule", "schedule.write.toggle"
    if re.search(r"\b(?:update|edit)\s+(?:the\s+)?schedule\b", lower):
        return "update_schedule", "schedule.write.update"
    return "create_schedule", "schedule.write.create"


def build_schedule_tool_plan(
    task: Task,
    *,
    skill_allowed: list[str] | None = None,
) -> ToolPlan | None:
    """Deterministic schedule plan so create-schedule is not replaced by a job template."""
    text = f"{task.cleaned_intent}\n{task.raw_text}".strip()
    if not looks_like_schedule_request(text):
        return None
    tool, intent_class = _schedule_action(text)
    allowed = set(skill_allowed or [])
    if allowed and tool not in allowed:
        return None

    args: dict[str, Any] = {}
    if tool == "create_schedule":
        name = extract_schedule_name(text)
        cron = extract_cron_expression(text)
        timezone = extract_schedule_timezone(text)
        if name:
            args["name"] = name
            args["instructions"] = (
                f"Run the existing playbook `{name}` for yesterday (IST). "
                "Do not recreate the playbook or generate slides in this turn."
            )
        if cron:
            args["cron_expression"] = cron
        if timezone:
            args["timezone"] = timezone

    return ToolPlan(
        goal="Create or manage a scheduled job",
        confidence=0.94,
        tools_needed=[tool],
        steps=[ToolPlanStep(tool, "manage schedule", args)],
        intent_class=intent_class,
        strategy="rules",
    )
