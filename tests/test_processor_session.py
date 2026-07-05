"""Tests for processor session memory."""

from __future__ import annotations

from unittest.mock import MagicMock

from backend.orchestrator.processor import TaskProcessor
from backend.models.config import default_config
from backend.models.task import Task
from backend.db.session_store import SessionStore


def test_processor_reuses_session_turns(tmp_path):
    config = default_config()
    store = SessionStore(tmp_path)
    mock_provider = MagicMock()
    mock_provider.chat.return_value = MagicMock(content="First reply", model="m")

    processor = TaskProcessor(config, session_store=store)
    processor.router = MagicMock()
    processor.router.get.return_value = mock_provider

    task = Task(
        source="slack",
        user_id="U1",
        channel_id="C1",
        thread_ts="100.1",
        raw_text="@alfred hi",
        cleaned_intent="hi",
    )
    processor.process(task)

    task2 = Task(
        source="slack",
        user_id="U1",
        channel_id="C1",
        thread_ts="100.1",
        raw_text="@alfred follow up",
        cleaned_intent="follow up",
    )
    processor.process(task2)

    assert mock_provider.chat.call_count == 2
    second_call_messages = mock_provider.chat.call_args_list[1].args[0]
    roles = [m.role for m in second_call_messages]
    assert roles.count("user") == 2
    assert roles.count("assistant") == 1


def test_processor_chat_fallback(tmp_path):
    from backend.models.config import AIConfig, AIProviderConfig

    config = default_config()
    # Configure two providers: ollama (primary) and openai (fallback)
    config.ai = AIConfig(
        default_provider="openai",
        routing={"basic_chat": {"provider": "ollama", "model": "llama3"}},
        providers={
            "ollama": AIProviderConfig(enabled=True, model="llama3"),
            "openai": AIProviderConfig(enabled=True, model="gpt-4o"),
        }
    )

    store = SessionStore(tmp_path)

    # Primary (Ollama) will raise an exception
    ollama_provider = MagicMock()
    ollama_provider.is_available.return_value = True
    ollama_provider.chat.side_effect = RuntimeError("Ollama connection failed")

    # Fallback (OpenAI) will succeed
    openai_provider = MagicMock()
    openai_provider.is_available.return_value = True
    openai_provider.chat.return_value = MagicMock(content="Fallback response content", model="gpt-4o")

    processor = TaskProcessor(config, session_store=store)
    processor.router = MagicMock()

    def get_side_effect(name: str):
        if name == "ollama":
            return ollama_provider
        return openai_provider

    processor.router.get.side_effect = get_side_effect

    task = Task(
        source="slack",
        user_id="U1",
        channel_id="C1",
        thread_ts="100.1",
        raw_text="@alfred hello",
        cleaned_intent="hello",
    )
    res = processor.process(task)
    assert res.text == "Fallback response content"
    assert openai_provider.chat.call_count == 1
