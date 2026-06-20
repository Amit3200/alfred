"""Tests for Slack thinking indicator."""

from __future__ import annotations

from unittest.mock import MagicMock

from backend.slack.status import (
    ASSISTANT_STATUS,
    ThinkingIndicator,
    loading_messages_for_slack,
)


def test_loading_messages_max_ten():
    messages = loading_messages_for_slack()
    assert len(messages) <= 10
    assert any("cooking" in m for m in messages)


def test_assistant_status_on_start_and_finish():
    client = MagicMock()
    client.assistant_threads_setStatus.return_value = {"ok": True}
    client.chat_postMessage.return_value = {"ts": "999"}

    indicator = ThinkingIndicator(client, channel="C1", thread_ts="100.1")
    indicator.start()

    client.assistant_threads_setStatus.assert_called_once()
    call = client.assistant_threads_setStatus.call_args.kwargs
    assert call["channel_id"] == "C1"
    assert call["thread_ts"] == "100.1"
    assert call["status"] == ASSISTANT_STATUS
    assert len(call["loading_messages"]) <= 10

    indicator.finish("Hello team.")
    assert client.chat_postMessage.called
    assert client.chat_postMessage.call_args.kwargs["text"] == "Hello team."
    # Cleared status then posted — at least 2 setStatus calls
    assert client.assistant_threads_setStatus.call_count >= 2


def test_legacy_fallback_when_assistant_unavailable():
    client = MagicMock()
    client.assistant_threads_setStatus.side_effect = Exception("missing_scope")
    client.chat_postMessage.return_value = {"ts": "888"}

    indicator = ThinkingIndicator(client, channel="C1", thread_ts="100.1")
    indicator.start()
    client.chat_postMessage.assert_called_once()

    indicator.finish("Done.")
    client.chat_update.assert_called_once()
