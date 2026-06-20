"""ReAct agent loop — LLM tool calls until a final answer."""

from __future__ import annotations

import json
import logging

from backend.ai.base import LLMProvider, LLMResponse, Message
from backend.ingress.git_direct import parse_text_tool_call
from backend.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

DEFAULT_MAX_ITERATIONS = 8


def run_agent_loop(
    provider: LLMProvider,
    messages: list[Message],
    registry: ToolRegistry,
    allowed_tools: list[str],
    *,
    model: str | None = None,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
) -> str:
    """Run tool-augmented chat until the model returns text or limits are hit."""
    tool_schemas = registry.get_schemas(allowed_tools)
    if not tool_schemas:
        raise RuntimeError("No tools available for the matched skill.")

    conversation = list(messages)

    for iteration in range(max_iterations):
        logger.debug("Agent loop iteration %d", iteration + 1)
        response = provider.chat(conversation, tools=tool_schemas, model=model)

        if response.tool_calls:
            conversation.append(_assistant_tool_message(response))
            for tool_call in response.tool_calls:
                observation = _execute_tool(
                    registry,
                    tool_call.name,
                    tool_call.arguments,
                    allowed=allowed_tools,
                )
                conversation.append(
                    Message(
                        role="tool",
                        content=observation,
                        tool_call_id=tool_call.id,
                        name=tool_call.name,
                    )
                )
            continue

        content = (response.content or "").strip()
        if content:
            parsed = parse_text_tool_call(content)
            if parsed:
                name, arguments = parsed
                if name in allowed_tools:
                    logger.info("Executing text-emitted tool call: %s", name)
                    _execute_tool(registry, name, arguments, allowed=allowed_tools)
                    return content
            return content

        return (
            "I ran the available tools but could not form a final answer. "
            "Try rephrasing or check Git integration settings."
        )

    return (
        "I hit the maximum number of investigation steps. "
        "Try a more specific question (e.g. repo name or PR number)."
    )


def _assistant_tool_message(response: LLMResponse) -> Message:
    summary = (response.content or "").strip()
    if not summary:
        names = ", ".join(tc.name for tc in response.tool_calls)
        summary = f"Calling tools: {names}"
    return Message(
        role="assistant",
        content=summary,
        tool_calls=list(response.tool_calls),
    )


def serialize_tool_arguments(arguments: dict) -> str:
    return json.dumps(arguments)


def _execute_tool(
    registry: ToolRegistry,
    name: str,
    arguments: dict,
    *,
    allowed: list[str],
) -> str:
    git = getattr(registry, "git_config", None)
    if git is not None:
        result = registry.run_normalized(name, arguments, allowed=allowed, git=git)
    else:
        result = registry.run(name, arguments, allowed=allowed)
    return result.to_json()
