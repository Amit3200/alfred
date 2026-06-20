"""Tests for OpenAI-compatible provider (Ollama local)."""

import sys
import types

from backend.ai.openai_compat import OpenAICompatProvider
from backend.models.config import AIProviderConfig


def test_ollama_available_without_api_key() -> None:
    cfg = AIProviderConfig(
        enabled=True,
        api_key="",
        base_url="http://127.0.0.1:11434/v1",
        model="llama3.2:3b",
    )
    provider = OpenAICompatProvider("ollama", cfg)
    assert provider.is_available() is True
    assert provider._is_local() is True


def test_ollama_client_uses_placeholder_key(monkeypatch) -> None:
    captured: dict = {}

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    fake_openai = types.ModuleType("openai")
    fake_openai.OpenAI = FakeOpenAI  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "openai", fake_openai)

    cfg = AIProviderConfig(
        enabled=True,
        api_key="",
        base_url="http://127.0.0.1:11434/v1",
        model="llama3.2:3b",
    )
    provider = OpenAICompatProvider("ollama", cfg)
    provider._get_client()
    assert captured.get("api_key") == "ollama"
    assert captured.get("base_url") == "http://127.0.0.1:11434/v1"
