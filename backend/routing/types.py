"""Core types for Alfred skill routing."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal

from backend.routing.playbooks import Playbook

RouteStrategy = Literal["keyword", "heuristic", "llm", "none"]


class RouteMode(str, Enum):
    """Which class of playbook/skill to resolve."""

    INVESTIGATION = "investigation"
    CONVERSATIONAL = "conversational"


@dataclass(frozen=True)
class RouteContext:
    """Input to the skill router."""

    intent: str
    channel_id: str = ""
    repo: str = ""
    mode: RouteMode = RouteMode.INVESTIGATION
    thread_context: str | None = None
    session_turns: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class RouteDecision:
    """How a skill was chosen (or not)."""

    skill_name: str | None
    strategy: RouteStrategy
    confidence: float = 1.0
    reason: str = ""

    @property
    def matched(self) -> bool:
        return bool(self.skill_name)


@dataclass(frozen=True)
class RouteResult:
    """Resolved playbook plus routing metadata."""

    playbook: Playbook | None
    decision: RouteDecision

    @classmethod
    def none(cls, *, reason: str = "no match") -> RouteResult:
        return cls(
            playbook=None,
            decision=RouteDecision(skill_name=None, strategy="none", confidence=0.0, reason=reason),
        )


@dataclass(frozen=True)
class SkillCatalogEntry:
    """Compact skill metadata for LLM routing (no markdown bodies)."""

    name: str
    description: str
    mode: str
    triggers: tuple[str, ...]
    tools: tuple[str, ...]
    repos: tuple[str, ...] = field(default_factory=tuple)

    def to_prompt_line(self, *, max_triggers: int = 4) -> str:
        shown = self.triggers[:max_triggers]
        trigger_text = ", ".join(f'"{token}"' for token in shown)
        if len(self.triggers) > max_triggers:
            trigger_text += f", +{len(self.triggers) - max_triggers} more"
        tools_text = ", ".join(self.tools[:6]) if self.tools else "none"
        if len(self.tools) > 6:
            tools_text += ", …"
        label = self.description or self.name.replace("_", " ")
        return (
            f"- **{self.name}** ({self.mode}) — {label}. "
            f"Triggers: {trigger_text or 'none'}. Tools: {tools_text}."
        )
