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
    provider.chat.return_value = LLMResponse(
        content='{"name":"list_my_prs","parameters{"state"": "open"}}',
        tool_calls=[],
    )

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

    assert "list_my_prs" in result
    assert registry.last_result is not None
    assert registry.last_result.kind == "pr_list"
