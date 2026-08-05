"""Autonomous agent loop runner (formerly Hermes) — delegates to unified agent runner."""

from __future__ import annotations

from typing import Any

from backend.agent.runner import run_agent
from backend.ai.base import LLMProvider, Message
from backend.tools.registry import ToolRegistry

DEFAULT_MAX_ITERATIONS = 20


def run_hermes_loop(
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
    """Run autonomous tool-augmented loop until final answer or iteration limit."""
    return run_agent(
        provider,
        messages,
        registry,
        allowed_tools,
        mode="autonomous",
        model=model,
        max_iterations=max_iterations,
        session=session,
        git=git,
    )
