"""Skill workflow_chain → ToolPlan (function chaining)."""

from __future__ import annotations

from typing import Any

from backend.routing.tool_plan_types import ToolPlan, ToolPlanStep
from backend.tools.base.chain import ToolChain


def chain_from_playbook(playbook: Any) -> ToolChain | None:
    tools = tuple(getattr(playbook, "workflow_chain", None) or ())
    if not tools:
        return None
    allowed = list(getattr(playbook, "allowed_tools", None) or [])
    if allowed:
        allow = set(allowed)
        tools = tuple(name for name in tools if name in allow)
    if not tools:
        return None
    return ToolChain(
        name=str(getattr(playbook, "name", "") or "workflow"),
        tools=tools,
        intent_class=str(getattr(playbook, "capability_bundle", "") or ""),
        goal=str(getattr(playbook, "description", "") or getattr(playbook, "name", "")),
    )


def plan_from_chain(chain: ToolChain, *, confidence: float = 0.86) -> ToolPlan:
    steps = [ToolPlanStep(tool=name, purpose=f"step {i + 1}") for i, name in enumerate(chain.tools)]
    return ToolPlan(
        goal=chain.goal or chain.name,
        confidence=confidence,
        tools_needed=list(chain.tools),
        steps=steps,
        strategy="workflow_chain",
        intent_class=chain.intent_class,
    )


def plan_from_playbook_chain(playbook: Any) -> ToolPlan | None:
    chain = chain_from_playbook(playbook)
    if chain is None:
        return None
    return plan_from_chain(chain)
