"""Plan templates — structured tool plans from `.alfred/playbooks/` triggers."""

from __future__ import annotations

import json
import re
from typing import Any

from backend.routing.playbooks import Playbook, PlaybookStore, _best_trigger_len
from backend.routing.tool_plan_types import ToolPlan, ToolPlanStep

_ISO_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_RUN_DATE_SUFFIX_RE = re.compile(
    r"\s+(?:for|on|dated?)\s+\d{4}-\d{2}-\d{2}\s*$",
    re.I,
)


def extract_iso_date(intent: str) -> str:
    """First YYYY-MM-DD in the user text, if any."""
    match = _ISO_DATE_RE.search(intent or "")
    return match.group(1) if match else ""


def strip_run_date_suffix(intent: str) -> str:
    """`run daily metrics oneshot for 2026-08-16` → `run daily metrics oneshot`."""
    return _RUN_DATE_SUFFIX_RE.sub("", (intent or "").strip()).strip()


def _inject_script_date(args_hint: dict[str, Any], report_date: str) -> None:
    if not report_date:
        return
    nested = args_hint.get("args")
    if nested is None:
        args_hint["args"] = {"date": report_date}
        return
    if isinstance(nested, dict) and "date" not in nested:
        nested["date"] = report_date


def planned_args_addendum(plan: ToolPlan | None) -> str:
    """Tell the worker to pass plan-template args (including a named report date)."""
    if plan is None:
        return ""
    lines: list[str] = []
    for step in plan.steps or []:
        if step.args_hint:
            lines.append(f"- `{step.tool}`: `{json.dumps(step.args_hint, sort_keys=True)}`")
    if not lines:
        return ""
    return (
        "\n\n## Planned tool arguments\n"
        "Call each tool with these arguments. If `args.date` is set, the user named that "
        "YYYY-MM-DD — do not omit it or substitute yesterday.\n"
        + "\n".join(lines)
    )


def list_plan_templates(store: PlaybookStore) -> list[Playbook]:
    return [pb for pb in store.list_playbooks() if pb.playbook_type == "plan_template"]


def match_plan_template(
    intent: str,
    store: PlaybookStore,
    *,
    channel_id: str = "",
    repo: str = "",
    min_confidence: float = 0.7,
) -> ToolPlan | None:
    """Match a plan template by trigger and convert to ToolPlan."""
    from backend.routing.schedule_intent import looks_like_schedule_request

    if looks_like_schedule_request(intent):
        return None
    lower = intent.lower()
    repo_lower = repo.strip().lower()
    best: Playbook | None = None
    best_len = 0

    for playbook in list_plan_templates(store):
        if playbook.channels and channel_id not in playbook.channels:
            continue
        if playbook.repos and repo_lower:
            from backend.routing.playbooks import _repo_matches

            if not _repo_matches(playbook.repos, lower, repo_lower):
                continue
        trigger_len = _best_trigger_len(playbook, lower)
        if trigger_len > best_len:
            best = playbook
            best_len = trigger_len

    if best is None or best_len == 0:
        return None

    template = best.plan_template or {}
    steps_raw = template.get("steps") if isinstance(template, dict) else None
    if not isinstance(steps_raw, list) or not steps_raw:
        return None

    steps: list[ToolPlanStep] = []
    tools: list[str] = []
    for item in steps_raw:
        if not isinstance(item, dict):
            continue
        tool = str(item.get("tool") or "").strip()
        if not tool:
            continue
        if tool not in tools:
            tools.append(tool)
        args_hint: dict[str, Any] = {}
        if isinstance(item.get("args"), dict):
            args_hint.update(item["args"])
        if item.get("title"):
            args_hint.setdefault("title", item["title"])
        if tool == "run_company_script":
            _inject_script_date(args_hint, extract_iso_date(intent))
        steps.append(
            ToolPlanStep(
                tool=tool,
                purpose=str(item.get("purpose") or best.description or best.name),
                args_hint=args_hint,
            )
        )

    if not tools:
        return None

    confidence = min(0.95, max(min_confidence, 0.72 + min(best_len, 20) * 0.01))
    report_date = extract_iso_date(intent)
    goal = str(template.get("goal") or best.description or f"Run plan template {best.name}")
    if report_date:
        goal = f"{goal.rstrip('.')} for {report_date}"
    return ToolPlan(
        goal=goal,
        confidence=confidence,
        tools_needed=tools,
        steps=steps,
        intent_class=str(template.get("intent_class") or f"template.{best.name}"),
        strategy="plan_template",
    )
