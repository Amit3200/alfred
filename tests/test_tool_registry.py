"""Tests for tool registry."""

from __future__ import annotations

from backend.ai.base import ToolSchema
from backend.tools.registry import ToolRegistry
from backend.tools.result import ToolResult


def test_registry_allowlist_blocks_tool():
    registry = ToolRegistry()
    schema = ToolSchema(
        name="demo_tool",
        description="Demo",
        parameters={"type": "object", "properties": {}, "required": []},
    )
    registry.register(schema, lambda _args: ToolResult(kind="text", data={"text": "ok"}))

    blocked = registry.run("demo_tool", {}, allowed=[])
    assert blocked.kind == "error"
    allowed = registry.run("demo_tool", {}, allowed=["demo_tool"])
    assert allowed.kind == "text"


def test_registry_unknown_tool():
    registry = ToolRegistry()
    result = registry.run("missing", {}, allowed=["missing"])
    assert result.kind == "error"
    assert "unknown tool" in result.data["message"]


def test_get_schemas_filters():
    registry = ToolRegistry()
    for name in ("a", "b"):
        registry.register(
            ToolSchema(
                name=name,
                description=name,
                parameters={"type": "object", "properties": {}, "required": []},
            ),
            lambda _args, n=name: ToolResult(kind="text", data={"text": n}),
        )
    schemas = registry.get_schemas(["b"])
    assert [s.name for s in schemas] == ["b"]
