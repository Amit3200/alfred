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
