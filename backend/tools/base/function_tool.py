"""Adapter so remaining register-style handlers share the BaseTool contract."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from backend.ai.base import ToolSchema
from backend.tools.base.tool import BaseTool, ToolContext
from backend.tools.result import ToolResult

ToolRunFn = Callable[[ToolContext, dict[str, Any]], ToolResult]


class FunctionTool(BaseTool):
    """Wrap a schema + ``run(ctx, args)`` function as a class-based tool."""

    def __init__(
        self,
        *,
        name: str,
        capability: str,
        operation: str,
        domain: str,
        schema: ToolSchema,
        run_fn: ToolRunFn,
        produces: tuple[str, ...] = (),
        consumes: tuple[str, ...] = (),
        next_tools: tuple[str, ...] = (),
    ) -> None:
        self.name = name
        self.capability = capability
        self.operation = operation
        self.domain = domain
        self.produces = produces
        self.consumes = consumes
        self.next_tools = next_tools
        self._schema = schema
        self._run_fn = run_fn

    def schema(self) -> ToolSchema:
        return self._schema

    def run(self, ctx: ToolContext, arguments: dict[str, Any]) -> ToolResult:
        return self._run_fn(ctx, arguments)
