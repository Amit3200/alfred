"""Class-based tool contract — one class per LLM operation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.ai.base import ToolSchema
from backend.models.config import AlfredConfig
from backend.tools.result import ToolResult


@dataclass(frozen=True)
class ToolContext:
    """Immutable runtime context for every tool invocation."""

    config: AlfredConfig
    data_dir: Path | None = None
    task_id: str | None = None
    session_key: str | None = None
    source: str = ""
    channel_id: str | None = None
    thread_ts: str | None = None
    user_id: str | None = None
    extra: dict[str, Any] | None = None

    @classmethod
    def from_registry(cls, registry: Any) -> ToolContext:
        """Build context from a ToolRegistry (task/config attached at execution)."""
        task = getattr(registry, "current_task", None)
        config = getattr(registry, "alfred_config", None)
        data_dir = getattr(registry, "data_dir", None)
        if config is None:
            raise RuntimeError("ToolRegistry is missing alfred_config.")
        path = Path(data_dir) if data_dir else None
        if task is None:
            return cls(config=config, data_dir=path, extra={"current_task": None, "registry": registry})
        return cls(
            config=config,
            data_dir=path,
            task_id=getattr(task, "id", None),
            source=str(getattr(task, "source", "") or ""),
            channel_id=getattr(task, "channel_id", None),
            thread_ts=getattr(task, "thread_ts", None),
            user_id=getattr(task, "user_id", None),
            extra={"current_task": task, "registry": registry},
        )

    def get(self, key: str, default: Any = None) -> Any:
        extra = self.extra or {}
        return extra.get(key, default)


class BaseTool(ABC):
    """One class = one LLM tool = one domain operation."""

    name: str
    capability: str
    operation: str
    domain: str
    produces: tuple[str, ...] = ()
    consumes: tuple[str, ...] = ()
    next_tools: tuple[str, ...] = ()

    @abstractmethod
    def schema(self) -> ToolSchema:
        """MCP-compatible JSON Schema for arguments."""

    @abstractmethod
    def run(self, ctx: ToolContext, arguments: dict[str, Any]) -> ToolResult:
        """Validate args, call domain service, return structured result."""

    def description(self) -> str:
        """Single-line text for planner manifest."""
        return self.schema().description

    def chain_hint(self) -> str:
        """How this tool composes with others (planner / skill workflows)."""
        parts: list[str] = []
        if self.consumes:
            parts.append("needs " + ", ".join(self.consumes))
        if self.produces:
            parts.append("emits " + ", ".join(self.produces))
        if self.next_tools:
            parts.append("then " + " → ".join(self.next_tools))
        return "; ".join(parts)

    def handler(self, registry: Any) -> Any:
        """Bind this tool to a registry for ToolRegistry.register()."""

        def _run(arguments: dict[str, Any]) -> ToolResult:
            ctx = ToolContext.from_registry(registry)
            return self.run(ctx, arguments)

        return _run
