"""Runtime context passed to LangGraph nodes (not serialized in state)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.ai.base import LLMProvider, Message
from backend.models.session import ConversationSession
from backend.models.task import Task
from backend.routing.goal_spec import GoalSpec
from backend.routing.playbooks import Playbook
from backend.routing.types import RouteContext


@dataclass
class GraphRuntime:
    processor: Any
    skill: Playbook
    messages: list[Message]
    provider: LLMProvider
    model: str
    task: Task
    session: ConversationSession | None
    route_context: RouteContext
    goal_spec: GoalSpec | None = None
    scoped_tools: list[str] | None = None
    manifest_text: str = ""
    _skill_override: Playbook | None = field(default=None, repr=False)

    @property
    def active_skill(self) -> Playbook:
        return self._skill_override or self.skill

    def set_skill(self, skill: Playbook) -> None:
        self._skill_override = skill


def get_runtime(config: dict[str, Any]) -> GraphRuntime:
    configurable = config.get("configurable") or {}
    runtime = configurable.get("runtime")
    if runtime is None:
        raise RuntimeError("LangGraph runtime missing from configurable context")
    return runtime
