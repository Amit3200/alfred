"""Tests for ReAct agent loop."""

from __future__ import annotations

from unittest.mock import MagicMock

from backend.agent.loop import run_agent_loop
from backend.ai.base import LLMResponse, Message, ToolCall, ToolSchema
from backend.tools.registry import ToolRegistry


def test_agent_loop_runs_tool_then_returns_answer():
    provider = MagicMock()
    provider.chat.side_effect = [
        LLMResponse(
            content=None,
            tool_calls=[
                ToolCall(id="call_1", name="echo", arguments={"text": "hello"}),
            ],
        ),
        LLMResponse(content="Done: hello", tool_calls=[]),
    ]

    registry = ToolRegistry()
    registry.register(
        ToolSchema(
            name="echo",
            description="Echo text",
            parameters={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        ),
        lambda args: str(args.get("text")),
    )

    result = run_agent_loop(
        provider,
        [Message(role="user", content="echo hello")],
        registry,
        ["echo"],
    )

    assert result == "Done: hello"
    assert provider.chat.call_count == 2


def test_agent_loop_respects_max_iterations():
    provider = MagicMock()
    provider.chat.return_value = LLMResponse(
        content=None,
        tool_calls=[ToolCall(id="c1", name="echo", arguments={"text": "x"})],
    )

    registry = ToolRegistry()
    registry.register(
        ToolSchema(
            name="echo",
            description="Echo",
            parameters={"type": "object", "properties": {"text": {"type": "string"}}, "required": []},
        ),
        lambda args: "x",
    )

    result = run_agent_loop(
        provider,
        [Message(role="user", content="loop")],
        registry,
        ["echo"],
        max_iterations=2,
    )

    assert "ran out of investigation steps" in result


def test_agent_loop_synthesizes_when_max_iterations():
    provider = MagicMock()
    provider.chat.side_effect = [
        LLMResponse(
            content=None,
            tool_calls=[ToolCall(id="c1", name="echo", arguments={"text": "x"})],
        ),
        LLMResponse(
            content=None,
            tool_calls=[ToolCall(id="c2", name="echo", arguments={"text": "y"})],
        ),
        LLMResponse(content="Currency uses updateCurrency in session.controller.ts", tool_calls=[]),
    ]

    registry = ToolRegistry()
    registry.register(
        ToolSchema(
            name="echo",
            description="Echo",
            parameters={"type": "object", "properties": {"text": {"type": "string"}}, "required": []},
        ),
        lambda args: "tool result",
    )

    result = run_agent_loop(
        provider,
        [Message(role="user", content="what do we use for currency change?")],
        registry,
        ["echo"],
        max_iterations=2,
    )

    assert result == "Currency uses updateCurrency in session.controller.ts"
    assert provider.chat.call_count == 3
    assert provider.chat.call_args_list[2].kwargs.get("tools") is None
