"""Tests for omitting polluted assistant session turns."""

from __future__ import annotations
from backend.integrations.slack.context import SlackContextBundle


from unittest.mock import MagicMock

from backend.orchestrator.policy import omit_assistant_session_history
from backend.orchestrator.processor import TaskProcessor
from backend.models.config import default_config
from backend.models.task import Task
from backend.db.session_store import SessionStore


def test_omit_assistant_on_history_lookup():
    assert omit_assistant_session_history(
        "when was the last duplicate order found?",
        include_context=True,
    )


def test_omit_assistant_on_tell_me_again():
    assert omit_assistant_session_history("can you tell me this again?", include_context=True)


def test_keep_assistant_history_during_pr_review_retry():
    assert not omit_assistant_session_history(
        "can you retry again?",
        include_context=True,
        pr_review_active=True,
    )


def test_processor_drops_assistant_turns_on_refresh(tmp_path):
    config = default_config()
    store = SessionStore(tmp_path)
    mock_provider = MagicMock()
    mock_provider.chat.return_value = MagicMock(content="Fresh answer", model="m")

    def fetch(_task):
        pass

        return SlackContextBundle(
            text="Channel messages (last 90 days):\n[1] line",
            channel_messages=[],
            history_window_label="last 90 days",
        )

    processor = TaskProcessor(config, session_store=store, context_fetcher=fetch)
    processor.router = MagicMock()
    processor.router.get.return_value = mock_provider

    task1 = Task(
        source="slack",
        user_id="U1",
        channel_id="C1",
        thread_ts="100.1",
        raw_text="@alfred when was last duplicate order?",
        cleaned_intent="when was last duplicate order?",
        metadata={"in_existing_thread": True},
    )
    processor.process(task1)

    task2 = Task(
        source="slack",
        user_id="U1",
        channel_id="C1",
        thread_ts="100.1",
        raw_text="@alfred can you tell me this again?",
        cleaned_intent="can you tell me this again?",
        metadata={"in_existing_thread": True},
    )
    processor.process(task2)

    second_messages = mock_provider.chat.call_args_list[-1].args[0]
    roles = [m.role for m in second_messages]
    assert roles.count("assistant") == 0
