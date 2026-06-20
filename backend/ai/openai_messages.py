"""Serialize LLM messages for OpenAI-compatible chat APIs."""

from __future__ import annotations

import json

from backend.ai.base import Message, ToolCall


def message_to_openai_api(message: Message) -> dict:
    if message.role == "tool":
        payload: dict = {
            "role": "tool",
            "content": message.content,
        }
        if message.tool_call_id:
            payload["tool_call_id"] = message.tool_call_id
        return payload

    if message.role == "assistant" and message.tool_calls:
        return {
            "role": "assistant",
            "content": message.content or None,
            "tool_calls": [_tool_call_to_openai(tc) for tc in message.tool_calls],
        }

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
