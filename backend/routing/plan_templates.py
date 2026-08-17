"""Plan templates — structured tool plans from `.alfred/playbooks/` triggers."""

from __future__ import annotations

from typing import Any

from backend.routing.playbooks import Playbook, PlaybookStore, _best_trigger_len
from backend.routing.tool_plan_types import ToolPlan, ToolPlanStep


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
    return ToolPlan(
        goal=str(template.get("goal") or best.description or f"Run plan template {best.name}"),
        confidence=confidence,
        tools_needed=tools,
        steps=steps,
        intent_class=str(template.get("intent_class") or f"template.{best.name}"),
        strategy="plan_template",
    )
