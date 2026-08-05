"""Serialize LLM messages for OpenAI-compatible chat APIs."""

from __future__ import annotations

import json

from backend.ai.base import Message, ToolCall


def assistant_message_content(message: Message) -> str:
    """Providers such as Kimi reject assistant turns with empty content."""
    content = (message.content or "").strip()
    if content:
        return content
    if message.tool_calls:
        names = ", ".join(tc.name for tc in message.tool_calls if tc.name)
        return f"Calling tools: {names}" if names else "Calling tools."
    return "Continuing."


def message_to_openai_api(message: Message) -> dict:
    if message.role == "tool":
        payload: dict = {
            "role": "tool",
            "content": message.content or "",
        }
        if message.tool_call_id:
            payload["tool_call_id"] = message.tool_call_id
        return payload

    if message.role == "assistant" and message.tool_calls:
        return {
            "role": "assistant",
            "content": assistant_message_content(message),
            "tool_calls": [_tool_call_to_openai(tc) for tc in message.tool_calls],
        }

    if message.role == "assistant":
        return {"role": "assistant", "content": assistant_message_content(message)}

    return {"role": message.role, "content": message.content}


def _tool_call_to_openai(tool_call: ToolCall) -> dict:
    return {
        "id": tool_call.id,
        "type": "function",
        "function": {
            "name": tool_call.name,
            "arguments": json.dumps(tool_call.arguments),
        },
    }
