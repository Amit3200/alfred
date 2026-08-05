"""Types for tool planning and scoped execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolPlanStep:
    tool: str
    purpose: str = ""
    args_hint: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolPlan:
    goal: str
    confidence: float
    tools_needed: list[str]
    steps: list[ToolPlanStep] = field(default_factory=list)
    missing_capabilities: list[str] = field(default_factory=list)
    strategy: str = "rules"
    intent_class: str = ""

    @property
    def satisfied(self) -> bool:
        return bool(self.tools_needed) and not self.missing_capabilities


@dataclass
class ScopedToolBinding:
    """Result of planning + validation for a single task turn."""

    plan: ToolPlan | None
    allowed_tools: list[str]
    manifest_text: str
    skill_name: str | None = None
