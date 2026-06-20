"""OpenAI-compatible adapter (Ollama, Groq, OpenAI, Together, etc.)."""

from __future__ import annotations

import json
from typing import Any

from backend.ai.base import LLMProvider, LLMResponse, Message, ToolCall, ToolSchema
from backend.models.config import AIProviderConfig


class OpenAICompatProvider(LLMProvider):
    name = "openai_compat"

    def __init__(self, provider_name: str, config: AIProviderConfig) -> None:
        self.provider_name = provider_name
        self.config = config
        self._client: Any = None

    def _is_local(self) -> bool:
        if self.provider_name == "ollama":
            return True
        base = (self.config.base_url or "").lower()
        return any(host in base for host in ("localhost", "127.0.0.1", "0.0.0.0"))

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise RuntimeError(
                    "openai package required. Install with: pip install alfred-agent[ai-openai]"
                ) from exc
            kwargs: dict[str, Any] = {}
            if self.config.api_key:
                kwargs["api_key"] = self.config.api_key
            elif self._is_local():
                # Ollama and other local OpenAI-compatible servers ignore the key.
                kwargs["api_key"] = "ollama"
            if self.config.base_url:
                kwargs["base_url"] = self.config.base_url
            self._client = OpenAI(**kwargs)
        return self._client

    def is_available(self) -> bool:
        if not self.config.enabled:
            return False
        if self._is_local():
            return True
        return bool(self.config.api_key)

    def chat(
        self,
        messages: list[Message],
        tools: list[ToolSchema] | None = None,
        model: str | None = None,
    ) -> LLMResponse:
        client = self._get_client()
        model_name = model or self.config.model
        payload_messages = [{"role": m.role, "content": m.content} for m in messages]
        kwargs: dict[str, Any] = {
            "model": model_name,
            "messages": payload_messages,
            "max_tokens": 4096,
        }
        if tools:
            kwargs["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in tools
            ]
        completion = client.chat.completions.create(**kwargs)
        choice = completion.choices[0]
        tool_calls: list[ToolCall] = []
        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                args = tc.function.arguments
                if isinstance(args, str):
                    args = json.loads(args)
                tool_calls.append(
                    ToolCall(id=tc.id, name=tc.function.name, arguments=args)
                )
        return LLMResponse(
            content=choice.message.content,
            tool_calls=tool_calls,
            model=model_name,
            provider=self.provider_name,
            raw=completion.model_dump() if hasattr(completion, "model_dump") else {},
        )
