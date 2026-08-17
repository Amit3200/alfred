"""Tool registry — schema-defined, allowlist-gated tool execution."""

from __future__ import annotations
from backend.observability.recorder import get_recorder
from backend.routing.git.context import enrich_tool_arguments
from backend.routing.git.direct import normalize_tool_arguments


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
        self._registration_filter: frozenset[str] | None = None
        self.last_result: ToolResult | None = None
        self.last_tool_name: str | None = None
        self.last_tool_args: dict[str, Any] | None = None
        self.tool_trace: list[dict[str, Any]] = []

    def set_registration_filter(self, allowed_tools: list[str] | None) -> None:
        """When set, ``register()`` skips tools not in this allowlist."""
        from backend.tools.selection import normalize_allowed

        self._registration_filter = normalize_allowed(allowed_tools)

    def clear_trace(self) -> None:
        self.tool_trace = []

    def clear_results(self) -> None:
        self.last_result = None
        self.last_tool_name = None
        self.last_tool_args = None
        self.tool_trace = []

    def record_trace(self, name: str, *, success: bool, result_kind: str, observation: str) -> None:
        self.tool_trace.append(
            {
                "tool": name,
                "success": success,
                "result_kind": result_kind,
                "observation": observation,
            }
        )

    def register(self, schema: ToolSchema, handler: ToolHandler) -> None:
        filt = self._registration_filter
        if filt is not None and schema.name not in filt:
            return
        self._tools[schema.name] = RegisteredTool(schema=schema, handler=handler)

    def register_tool(self, tool: Any, *, extra: dict[str, Any] | None = None) -> None:
        """Register a BaseTool instance (class-based tools)."""
        schema = tool.schema()
        filt = self._registration_filter
        if filt is not None and schema.name not in filt:
            return

        def handler(arguments: dict[str, Any]) -> ToolResult:
            from backend.tools.base.tool import ToolContext

            ctx = ToolContext.from_registry(self)
            extra_map = dict(ctx.extra or {})
            if extra:
                extra_map.update(extra)
            ctx = ToolContext(
                config=ctx.config,
                data_dir=ctx.data_dir,
                task_id=ctx.task_id,
                session_key=ctx.session_key,
                source=ctx.source,
                channel_id=ctx.channel_id,
                thread_ts=ctx.thread_ts,
                user_id=ctx.user_id,
                extra=extra_map,
            )
            return tool.run(ctx, arguments)

        self._tools[schema.name] = RegisteredTool(schema=schema, handler=handler)

    def get_schemas(self, allowed: list[str]) -> list[ToolSchema]:
        return [self._tools[name].schema for name in allowed if name in self._tools]

    def run(self, name: str, arguments: dict[str, Any], *, allowed: list[str]) -> ToolResult:
        if name not in allowed:
            return ToolResult.error(f"tool {name!r} is not allowed for this skill.")
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult.error(f"unknown tool {name!r}.")

        gov: Any = getattr(self, "governance", None)
        if gov is not None:
            blocked = gov.check_before_run(name, arguments)
            if blocked is not None:
                self.last_result = blocked
                self.last_tool_name = name
                self.last_tool_args = dict(arguments)
                return blocked

        try:
            result = tool.handler(arguments)
            self.last_result = result
            self.last_tool_name = name
            self.last_tool_args = dict(arguments)
            logger.info("Tool %s completed kind=%s", name, result.kind)
            self._record_tool(name, success=result.kind != "error")
            if gov is not None:
                gov.audit_after_run(name, arguments, result)
            return result
        except Exception as exc:
            logger.exception("Tool %s failed", name)
            result = ToolResult.error(f"Error running {name}: {exc}")
            self.last_result = result
            self.last_tool_name = name
            self.last_tool_args = dict(arguments)
            self._record_tool(name, success=False)
            if gov is not None:
                gov.audit_after_run(name, arguments, result)
            return result

    def _record_tool(self, name: str, *, success: bool) -> None:
        try:
            pass

            data_dir = getattr(self, "data_dir", None)
            get_recorder(data_dir).record_tool_call(name, success=success)
        except Exception:
            logger.debug("Tool observability recording skipped", exc_info=True)

    def run_normalized(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        allowed: list[str],
        git: Any,
        session: Any | None = None,
    ) -> ToolResult:
        pass
        pass

        normalized = normalize_tool_arguments(name, arguments, git)
        normalized = enrich_tool_arguments(name, normalized, git, session)
        return self.run(name, normalized, allowed=allowed)
