"""Anthropic Claude adapter."""

from __future__ import annotations

from typing import Any

from backend.ai.base import LLMProvider, LLMResponse, Message, ToolCall, ToolSchema
from backend.ai.tool_arguments import parse_tool_call_arguments
from backend.models.config import AIProviderConfig


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, config: AIProviderConfig) -> None:
        self.config = config
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                import anthropic
            except ImportError as exc:
                raise RuntimeError(
                    "anthropic package required. Install with: pip install alfred-agent[ai-anthropic]"
                ) from exc
            self._client = anthropic.Anthropic(api_key=self.config.api_key)
        return self._client

    def is_available(self) -> bool:
        return self.config.enabled and bool(self.config.api_key)

    def chat(
        self,
        messages: list[Message],
        tools: list[ToolSchema] | None = None,
        model: str | None = None,
    ) -> LLMResponse:
        client = self._get_client()
        model_name = model or self.config.model
        system = "\n".join(m.content for m in messages if m.role == "system")
        api_messages = _anthropic_messages(messages)
        kwargs: dict[str, Any] = {
            "model": model_name,
            "max_tokens": 4096,
            "messages": api_messages,
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.parameters,
                }
                for t in tools
            ]
        response = client.messages.create(**kwargs)
        content_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in response.content:
            if block.type == "text":
                content_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCall(
                        id=block.id,
                        name=block.name,
                        arguments=parse_tool_call_arguments(
                            block.input,
                            tool_name=block.name or "",
                        ),
                    )
                )
        return LLMResponse(
            content="\n".join(content_parts) or None,
            tool_calls=tool_calls,
            model=model_name,
            provider="anthropic",
            raw=response.model_dump() if hasattr(response, "model_dump") else {},
        )


def _anthropic_messages(messages: list[Message]) -> list[dict]:
    """Convert normalized messages to Anthropic API format (including tool turns)."""
    api_messages: list[dict] = []
    for message in messages:
        if message.role == "system":
            continue
        if message.role == "tool":
            api_messages.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": message.tool_call_id or message.name or "tool",
                            "content": message.content,
                        }
                    ],
                }
            )
            continue
        if message.role == "assistant" and message.tool_calls:
            content_blocks: list[dict] = []
            if message.content:
                content_blocks.append({"type": "text", "text": message.content})
            for tool_call in message.tool_calls:
                content_blocks.append(
                    {
                        "type": "tool_use",
                        "id": tool_call.id,
                        "name": tool_call.name,
                        "input": tool_call.arguments,
                    }
                )
            api_messages.append({"role": "assistant", "content": content_blocks})
            continue
        api_messages.append({"role": message.role, "content": message.content})
    return api_messages
