"""Tests for text-emitted tool calls in agent loop."""

from __future__ import annotations

from unittest.mock import MagicMock

from backend.agent.loop import run_agent_loop
from backend.ai.base import LLMResponse, Message, ToolSchema
from backend.git.api import PullRequestSummary
from backend.tools.registry import ToolRegistry
from backend.tools.result import ToolResult


def test_agent_loop_executes_text_tool_call():
    provider = MagicMock()
    provider.chat.side_effect = [
        LLMResponse(
            content='{"name":"list_my_prs","parameters{"state"": "open"}}',
            tool_calls=[],
        ),
        LLMResponse(content="You have 1 open PR.", tool_calls=[]),
    ]

    registry = ToolRegistry()

    def handler(_args):
        return ToolResult.pr_list(
            [
                PullRequestSummary(
                    number=1,
                    title="Test",
                    state="open",
                    repo="org/repo",
                    author="alice",
                    url="https://example.com/pull/1",
                )
            ],
            state="open",
        )

    registry.register(
        ToolSchema(
            name="list_my_prs",
            description="List my PRs",
            parameters={"type": "object", "properties": {}, "required": []},
        ),
        handler,
    )

    result = run_agent_loop(
        provider,
        [Message(role="user", content="my open prs")],
        registry,
        ["list_my_prs"],
    )

    assert result == "You have 1 open PR."
    assert provider.chat.call_count == 2
    assert registry.last_result is not None
    assert registry.last_result.kind == "pr_list"


def test_agent_loop_executes_kimi_tool_tag():
    provider = MagicMock()
    provider.chat.side_effect = [
        LLMResponse(
            content=(
                "I'll search the codebase.\n\n"
                '<tool>{"tool_type": "function", "tool_name": "grep_repo", '
                '"tool_input": {"pattern": "recalculation", "path": "FlexyPe/cipher"}}</tool>'
            ),
            tool_calls=[],
        ),
        LLMResponse(content="The recalculation method does X, Y, Z.", tool_calls=[]),
    ]

    registry = ToolRegistry()
    registry.register(
        ToolSchema(
            name="grep_repo",
            description="Search repo",
            parameters={
                "type": "object",
                "properties": {"pattern": {"type": "string"}},
                "required": ["pattern"],
            },
        ),
        lambda args: ToolResult(kind="grep", data={"matches": []}),
    )

    result = run_agent_loop(
        provider,
        [Message(role="user", content="what does recalculation do?")],
        registry,
        ["grep_repo"],
    )

    assert result == "The recalculation method does X, Y, Z."
    assert "<tool>" not in result
    assert registry.last_tool_name == "grep_repo"
