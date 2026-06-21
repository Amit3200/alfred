"""LLM provider wrapper that records observability events."""

from __future__ import annotations

import time
from typing import Iterator

from backend.ai.base import LLMChunk, LLMProvider, LLMResponse, Message, ToolSchema
from backend.observability.recorder import ObservabilityRecorder


class InstrumentedLLMProvider(LLMProvider):
    def __init__(
        self,
        inner: LLMProvider,
        *,
        provider_name: str,
        recorder: ObservabilityRecorder,
    ) -> None:
        self._inner = inner
        self.provider_name = provider_name
        self._recorder = recorder
        self.name = inner.name

    def is_available(self) -> bool:
        return self._inner.is_available()

    def chat(
        self,
        messages: list[Message],
        tools: list[ToolSchema] | None = None,
        model: str | None = None,
    ) -> LLMResponse:
        started = time.perf_counter()
        response = self._inner.chat(messages, tools=tools, model=model)
        duration_ms = int((time.perf_counter() - started) * 1000)
        if not response.provider:
            response.provider = self.provider_name
        self._recorder.record_llm_call(response, duration_ms=duration_ms)
        return response

    def stream(
        self,
        messages: list[Message],
        tools: list[ToolSchema] | None = None,
        model: str | None = None,
    ) -> Iterator[LLMChunk]:
        return self._inner.stream(messages, tools=tools, model=model)
