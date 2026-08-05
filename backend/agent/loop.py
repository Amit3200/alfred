"""ReAct agent loop — LLM tool calls until a final answer."""

from __future__ import annotations

from typing import Any

from backend.agent.runner import run_agent
from backend.ai.base import LLMProvider, Message
from backend.tools.registry import ToolRegistry

DEFAULT_MAX_ITERATIONS = 20


def run_agent_loop(
    provider: LLMProvider,
    messages: list[Message],
    registry: ToolRegistry,
    allowed_tools: list[str],
    *,
    model: str | None = None,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    session: Any | None = None,
    git: Any | None = None,
) -> str:
    return run_agent(
        provider,
        messages,
        registry,
        allowed_tools,
        mode="react",
        model=model,
        max_iterations=max_iterations,
        session=session,
        git=git,
    )


def _execute_tool(
    registry: ToolRegistry,
    name: str,
    arguments: dict,
    *,
    allowed: list[str],
    session: Any | None = None,
    git: Any | None = None,
) -> str:
    """Backward-compatible export used by tests and hermes_runner shim."""
    from backend.agent.execute import execute_tool

    return execute_tool(
        registry,
        name,
        arguments,
        allowed=allowed,
        session=session,
        git=git,
    )


def serialize_tool_arguments(arguments: dict) -> str:
    import json

    return json.dumps(arguments)
