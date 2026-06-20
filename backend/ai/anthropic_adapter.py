"""Anthropic Claude adapter."""

from __future__ import annotations

import json
from typing import Any

from backend.ai.base import LLMProvider, LLMResponse, Message, ToolCall, ToolSchema
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
        api_messages = [
            {"role": m.role, "content": m.content}
            for m in messages
            if m.role in ("user", "assistant")
        ]
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
                        arguments=block.input if isinstance(block.input, dict) else json.loads(block.input),
                    )
                )
        return LLMResponse(
            content="\n".join(content_parts) or None,
            tool_calls=tool_calls,
            model=model_name,
            provider="anthropic",
            raw=response.model_dump() if hasattr(response, "model_dump") else {},
        )
