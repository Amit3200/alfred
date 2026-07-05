from backend.ai.base import Message

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


def test_kimi_requires_api_key() -> None:
    cfg = AIProviderConfig(
        enabled=True,
        api_key="",
        base_url="https://api.moonshot.ai/v1",
        model="kimi-k2.6",
    )
    provider = OpenAICompatProvider("kimi", cfg)
    assert provider.is_available() is False
    assert provider._is_local() is False

    cfg.api_key = "sk-test"
    assert provider.is_available() is True


def test_kimi_chat_disables_thinking_and_falls_back_to_reasoning(monkeypatch) -> None:
    captured: dict = {}

    class FakeMessage:
        content = None
        tool_calls = None
        reasoning_content = "Summarized tickets by severity."

    class FakeChoice:
        message = FakeMessage()

    class FakeCompletion:
        choices = [FakeChoice()]

        @staticmethod
        def model_dump() -> dict:
            return {}

    class FakeCompletions:
        @staticmethod
        def create(**kwargs):
            captured.update(kwargs)
            return FakeCompletion()

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    cfg = AIProviderConfig(
        enabled=True,
        api_key="sk-test",
        base_url="https://api.moonshot.ai/v1",
        model="kimi-k2.6",
    )
    provider = OpenAICompatProvider("kimi", cfg)
    monkeypatch.setattr(provider, "_get_client", lambda: FakeClient())

    pass

    response = provider.chat([Message(role="user", content="hello")])
    assert captured.get("extra_body") == {"thinking": {"type": "disabled"}}
    assert response.content == "Summarized tickets by severity."
