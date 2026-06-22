"""Tests for Slack thinking indicator."""

from __future__ import annotations

import random
from unittest.mock import MagicMock

from backend.slack.status import (
    ASSISTANT_STATUS,
    STATUS_LINES,
    ThinkingIndicator,
    loading_line_to_status,
    loading_messages_for_slack,
)


def test_loading_messages_max_ten():
    messages = loading_messages_for_slack()
    assert len(messages) == 10
    assert all(message.strip() for message in messages)


def test_loading_messages_mixes_custom_and_defaults(monkeypatch):
    custom = [
        ":this_is_fine: Everything is fine. Checking prod…",
        ":rollsafe: Big brain debugging…",
    ]
    defaults = {f"{emoji} {line}" for emoji, line in STATUS_LINES}

    def sample_first(pool: list[str], count: int) -> list[str]:
        return pool[:count]

    monkeypatch.setattr(random, "sample", sample_first)
    messages = loading_messages_for_slack(custom_lines=custom)

    assert len(messages) == 10
    assert messages[:2] == custom
    assert any(message in defaults for message in messages[2:])


def test_loading_messages_returns_full_merged_pool_when_under_limit():
    custom = [":doge: Much query.", ":cat: Meow."]
    messages = loading_messages_for_slack(custom_lines=custom, count=1000)
    assert messages[:2] == custom
    assert len(messages) == 2 + len(STATUS_LINES)


def test_loading_messages_samples_from_merged_pool():
    custom = [f":emoji_{index}: line {index}" for index in range(12)]
    messages = loading_messages_for_slack(custom_lines=custom)
    assert len(messages) == 10
    defaults = {f"{emoji} {line}" for emoji, line in STATUS_LINES}
    assert all(message in set(custom) or message in defaults for message in messages)


def test_assistant_status_uses_mixed_loading_messages(monkeypatch):
    client = MagicMock()
    client.assistant_threads_setStatus.return_value = {"ok": True}
    custom = [":doge: Much query. Very wait."]

    def sample_first(pool: list[str], count: int) -> list[str]:
        return pool[:count]

    monkeypatch.setattr(random, "sample", sample_first)

    indicator = ThinkingIndicator(
        client,
        channel="C1",
        thread_ts="100.1",
        loading_messages=custom,
    )
    indicator.start()

    call = client.assistant_threads_setStatus.call_args.kwargs
    assert call["loading_messages"][0] == custom[0]
    assert any("cooking" in message for message in call["loading_messages"])


def test_loading_line_to_status():
    assert loading_line_to_status("🍳 I am cooking…") == "is cooking…"
    assert loading_line_to_status(":this_is_fine: Everything is fine.") == "is everything is fine."
    assert loading_line_to_status("is thinking…") == "is thinking…"


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
    assert call["status"].startswith("is ")
    assert len(call["loading_messages"]) <= 10

    indicator.finish("Hello team.")
    assert client.chat_postMessage.called
    assert client.chat_postMessage.call_args.kwargs["text"] == "Hello team."
    # Cleared status then posted — at least 2 setStatus calls
    assert client.assistant_threads_setStatus.call_count >= 2


def test_status_rotation_updates_assistant_status(monkeypatch):
    client = MagicMock()
    client.assistant_threads_setStatus.return_value = {"ok": True}

    def fast_wait(_seconds: float) -> bool:
        return True

    indicator = ThinkingIndicator(client, channel="C1", thread_ts="100.1", rotation_seconds=0.01)
    monkeypatch.setattr(indicator._stop_rotation, "wait", fast_wait)
    indicator.start()
    indicator.finish("Done.")

    assert client.assistant_threads_setStatus.call_count >= 2
    statuses = [
        call.kwargs["status"]
        for call in client.assistant_threads_setStatus.call_args_list
        if call.kwargs.get("status")
    ]
    assert any(status.startswith("is ") for status in statuses)


def test_legacy_fallback_when_assistant_unavailable():
    client = MagicMock()
    client.assistant_threads_setStatus.side_effect = Exception("missing_scope")
    client.chat_postMessage.return_value = {"ts": "888"}

    indicator = ThinkingIndicator(client, channel="C1", thread_ts="100.1")
    indicator.start()
    client.chat_postMessage.assert_called_once()

    indicator.finish("Done.")
    client.chat_update.assert_called_once()
