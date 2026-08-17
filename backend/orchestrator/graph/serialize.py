"""Serialize tool plans and goal specs for LangGraph state."""

from __future__ import annotations

from typing import Any

from backend.routing.goal_spec import GoalSpec
from backend.routing.tool_plan_types import ToolPlan, ToolPlanStep


def tool_plan_to_dict(plan: ToolPlan | None) -> dict[str, Any] | None:
    if plan is None:
        return None
    return {
        "goal": plan.goal,
        "confidence": plan.confidence,
        "tools_needed": list(plan.tools_needed),
        "steps": [
            {"tool": s.tool, "purpose": s.purpose, "args_hint": dict(s.args_hint)}
            for s in plan.steps
        ],
        "missing_capabilities": list(plan.missing_capabilities),
        "strategy": plan.strategy,
        "intent_class": plan.intent_class,
    }


def tool_plan_from_dict(data: dict[str, Any] | None) -> ToolPlan | None:
    if not data:
        return None
    steps = [
        ToolPlanStep(
            tool=str(s.get("tool") or ""),
            purpose=str(s.get("purpose") or ""),
            args_hint=dict(s.get("args_hint") or {}),
        )
        for s in data.get("steps") or []
    ]
    return ToolPlan(
        goal=str(data.get("goal") or ""),
        confidence=float(data.get("confidence") or 0.0),
        tools_needed=[str(t) for t in data.get("tools_needed") or []],
        steps=steps,
        missing_capabilities=[str(m) for m in data.get("missing_capabilities") or []],
        strategy=str(data.get("strategy") or ""),
        intent_class=str(data.get("intent_class") or ""),
    )


def goal_spec_to_dict(spec: GoalSpec | None) -> dict[str, Any] | None:
    if spec is None:
        return None
    return {
        "intent_class": spec.intent_class,
        "goal": spec.goal,
        "required_tools": list(spec.required_tools),
        "success_criteria": list(spec.success_criteria),
        "failure_response": spec.failure_response,
        "requires_write": spec.requires_write,
    }


def goal_spec_from_dict(data: dict[str, Any] | None) -> GoalSpec | None:
    if not data:
        return None
    return GoalSpec(
        intent_class=str(data.get("intent_class") or ""),
        goal=str(data.get("goal") or ""),
        required_tools=[str(t) for t in data.get("required_tools") or []],
        success_criteria=[str(c) for c in data.get("success_criteria") or []],
        failure_response=str(data.get("failure_response") or ""),
        requires_write=bool(data.get("requires_write")),
    )
