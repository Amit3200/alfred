"""Capability-scoped tool bundles."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from backend.tools.base.tool import BaseTool
from backend.tools.registry import ToolRegistry


class ToolBundle(ABC):
    """Registers a coherent capability slice (e.g. all JIRA write tools)."""

    capability_prefix: str = ""

    @abstractmethod
    def tools(self) -> list[BaseTool]:
        """Return tool instances in this bundle."""

    def tool_names(self) -> list[str]:
        return [tool.name for tool in self.tools()]

    def descriptions(self) -> dict[str, str]:
        return {tool.name: tool.description() for tool in self.tools()}

    def register(self, registry: ToolRegistry, *, extra: dict[str, Any] | None = None) -> None:
        """Register every tool on the registry using class-based handlers."""
        for tool in self.tools():
            registry.register_tool(tool, extra=extra)
