"""Google Gemini adapter."""

from __future__ import annotations

import json
from typing import Any

from backend.ai.base import LLMProvider, LLMResponse, Message, ToolCall, ToolSchema
from backend.models.config import AIProviderConfig


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self, config: AIProviderConfig) -> None:
        self.config = config
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                from google import genai
            except ImportError as exc:
                raise RuntimeError(
                    "google-genai required. Install with: pip install alfred-agent[ai-gemini]"
                ) from exc
            self._client = genai.Client(api_key=self.config.api_key)
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
        contents = [
            {"role": "user" if m.role == "user" else "model", "parts": [{"text": m.content}]}
            for m in messages
            if m.role in ("user", "assistant", "system")
        ]
        kwargs: dict[str, Any] = {"model": model_name, "contents": contents}
        if tools:
            kwargs["config"] = {
                "tools": [
                    {
                        "function_declarations": [
                            {
                                "name": t.name,
                                "description": t.description,
                                "parameters": t.parameters,
                            }
                            for t in tools
                        ]
                    }
                ]
            }
        response = client.models.generate_content(**kwargs)
        text = getattr(response, "text", None) or ""
        tool_calls: list[ToolCall] = []
        candidates = getattr(response, "candidates", None) or []
        for candidate in candidates:
            content = getattr(candidate, "content", None)
            if not content:
                continue
            for part in getattr(content, "parts", []) or []:
                fn = getattr(part, "function_call", None)
                if fn:
                    args = dict(fn.args) if hasattr(fn, "args") else {}
                    tool_calls.append(
                        ToolCall(
                            id=fn.name,
                            name=fn.name,
                            arguments=args,
                        )
                    )
        return LLMResponse(
            content=text or None,
            tool_calls=tool_calls,
            model=model_name,
            provider="gemini",
            raw={},
        )
