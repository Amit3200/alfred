"""Tool registry — schema-defined, allowlist-gated tool execution."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from backend.ai.base import ToolSchema
from backend.tools.result import ToolResult

logger = logging.getLogger(__name__)

ToolHandler = Callable[[dict[str, Any]], ToolResult]


@dataclass
class RegisteredTool:
    schema: ToolSchema
    handler: ToolHandler


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}
        self.last_result: ToolResult | None = None
        self.last_tool_name: str | None = None
        self.last_tool_args: dict[str, Any] | None = None

    def clear_results(self) -> None:
        self.last_result = None
        self.last_tool_name = None
        self.last_tool_args = None

    def register(self, schema: ToolSchema, handler: ToolHandler) -> None:
        self._tools[schema.name] = RegisteredTool(schema=schema, handler=handler)

    def get_schemas(self, allowed: list[str]) -> list[ToolSchema]:
        return [self._tools[name].schema for name in allowed if name in self._tools]

    def run(self, name: str, arguments: dict[str, Any], *, allowed: list[str]) -> ToolResult:
        if name not in allowed:
            return ToolResult.error(f"tool {name!r} is not allowed for this skill.")
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult.error(f"unknown tool {name!r}.")
        try:
            result = tool.handler(arguments)
            self.last_result = result
            self.last_tool_name = name
            self.last_tool_args = dict(arguments)
            logger.info("Tool %s completed kind=%s", name, result.kind)
            return result
        except Exception as exc:
            logger.exception("Tool %s failed", name)
            result = ToolResult.error(f"Error running {name}: {exc}")
            self.last_result = result
            self.last_tool_name = name
            self.last_tool_args = dict(arguments)
            return result

    def run_normalized(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        allowed: list[str],
        git: Any,
        session: Any | None = None,
    ) -> ToolResult:
        from backend.ingress.git_context import enrich_tool_arguments
        from backend.ingress.git_direct import normalize_tool_arguments

        normalized = normalize_tool_arguments(name, arguments, git)
        normalized = enrich_tool_arguments(name, normalized, git, session)
        return self.run(name, normalized, allowed=allowed)
