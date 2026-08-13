"""Tests for instrumented LLM provider wrapper."""

from __future__ import annotations

from backend.ai.base import LLMProvider, LLMResponse, Message
from backend.observability.instrumentation import InstrumentedLLMProvider
from backend.observability.recorder import ObservabilityRecorder


class _StubProvider(LLMProvider):
    name = "stub"

    def __init__(self) -> None:
        self.last_max_tokens: int | None = None

    def chat(self, messages, tools=None, model=None, max_tokens=None):
        self.last_max_tokens = max_tokens
        return LLMResponse(content="ok", provider="stub")


def test_instrumented_provider_forwards_max_tokens(tmp_path):
    inner = _StubProvider()
    recorder = ObservabilityRecorder(tmp_path)
    provider = InstrumentedLLMProvider(inner, provider_name="stub", recorder=recorder)
    provider.chat([Message(role="user", content="hi")], max_tokens=16384)
    assert inner.last_max_tokens == 16384
