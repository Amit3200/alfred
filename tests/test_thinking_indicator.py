"""Tests for Slack thinking indicator."""

from __future__ import annotations
from slack_sdk.errors import SlackApiError


import random
from unittest.mock import MagicMock

from backend.integrations.slack.status import (
    ASSISTANT_STATUS,
    MAX_SLACK_LOADING_MESSAGE_LENGTH,
    STATUS_LINES,
    ThinkingIndicator,
    build_loading_pool,
    loading_line_to_status,
    loading_messages_for_slack,
    pool_has_custom_shortcodes,
    slack_loading_messages,
    slack_shortcode_prefix,
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
    assert all(line in messages for line in custom)
    assert any(message in defaults for message in messages)


def test_loading_messages_returns_full_merged_pool_when_under_limit():
    custom = [":doge: Much query.", ":cat: Meow."]
    messages = build_loading_pool(custom_lines=custom)
    assert messages[:2] == custom
    assert len(messages) == 2 + len(STATUS_LINES)


def test_loading_messages_includes_defaults_when_many_custom(monkeypatch):
    custom = [f":emoji_{index}: line {index}" for index in range(12)]
    defaults = {f"{emoji} {line}" for emoji, line in STATUS_LINES}

    def sample_first(pool: list[str], count: int) -> list[str]:
        return pool[:count]

    monkeypatch.setattr(random, "sample", sample_first)
    messages = loading_messages_for_slack(custom_lines=custom)

    assert len(messages) == 10
    assert any(message in defaults for message in messages)
    assert any(message.startswith(":emoji_") for message in messages)


def test_build_loading_pool_includes_all_defaults_with_many_custom():
    custom = [f":emoji_{index}: line {index}" for index in range(21)]
    pool = build_loading_pool(custom_lines=custom)
    assert pool[:21] == custom
    assert len(pool) == 21 + len(STATUS_LINES)
    assert pool[21].startswith("🍳")


def test_slack_loading_messages_truncates_long_custom_lines():
    custom = [":this_is_fine: Everything is fine. Checking prod…"]
    sanitized = slack_loading_messages(custom)
    assert len(sanitized) == 1
    assert sanitized[0].startswith(":this_is_fine:")
    assert len(sanitized[0]) <= MAX_SLACK_LOADING_MESSAGE_LENGTH


def test_slack_loading_messages_keeps_short_emoji_lines():
    custom = [":doge: Much query. Very wait.", "😸 Cat is sitting on the router again…"]
    sanitized = slack_loading_messages(custom)
    assert sanitized[0] == ":doge: Much query. Very wait."
    assert sanitized[1] == "😸 Cat is sitting on the router again…"


def test_slack_loading_messages_truncates_long_lines_but_keeps_emoji():
    custom = [":this-is-fine-fire: This is fine. Everything is fine."]
    sanitized = slack_loading_messages(custom)
    assert sanitized[0].startswith(":this-is-fine-fire:")
    assert sanitized[0].endswith("…")
    assert len(sanitized[0]) <= MAX_SLACK_LOADING_MESSAGE_LENGTH


def test_assistant_status_uses_unicode_loading_messages(monkeypatch):
    client = MagicMock()
    client.assistant_threads_setStatus.return_value = {"ok": True}

    def empty_custom(_custom_lines):
        return []

    monkeypatch.setattr(
        "backend.integrations.slack.status.loading_messages_for_slack",
        lambda **kwargs: [f"{emoji} {line}" for emoji, line in STATUS_LINES[:3]],
    )

    indicator = ThinkingIndicator(client, channel="C1", thread_ts="100.1")
    indicator.start()

    call = client.assistant_threads_setStatus.call_args.kwargs
    assert call["loading_messages"][0].startswith("🍳")
    assert "icon_emoji" not in call
    assert all(len(message) <= MAX_SLACK_LOADING_MESSAGE_LENGTH for message in call["loading_messages"])


def test_custom_shortcodes_use_legacy_thinking_message():
    client = MagicMock()
    client.assistant_threads_setStatus.return_value = {"ok": True}
    client.chat_postMessage.return_value = {"ts": "111"}
    custom = [":this_is_fine: Everything is fine. Checking prod…"]

    indicator = ThinkingIndicator(
        client,
        channel="C1",
        thread_ts="100.1",
        loading_messages=custom,
    )
    indicator.start()

    client.assistant_threads_setStatus.assert_not_called()
    client.chat_postMessage.assert_called_once()
    assert ":this_is_fine:" in client.chat_postMessage.call_args.kwargs["text"]


def test_slack_shortcode_prefix():
    assert slack_shortcode_prefix(":batman-interesting: Interesting…") == ":batman-interesting:"
    assert pool_has_custom_shortcodes([":doge: Much query."]) is True
    assert pool_has_custom_shortcodes(["🦇 Batman is searching…"]) is False


def test_assistant_status_does_not_rotate_status_text(monkeypatch):
    client = MagicMock()
    client.assistant_threads_setStatus.return_value = {"ok": True}

    def fast_wait(_seconds: float) -> bool:
        return True

    indicator = ThinkingIndicator(client, channel="C1", thread_ts="100.1", rotation_seconds=0.01)
    monkeypatch.setattr(indicator._stop_rotation, "wait", fast_wait)
    indicator.start()
    indicator.finish("Done.")

    status_updates = [
        call.kwargs.get("status")
        for call in client.assistant_threads_setStatus.call_args_list
        if call.kwargs.get("status")
    ]
    # Initial status + clear on finish — no rapid text churn in between.
    assert len(status_updates) <= 2
    assert status_updates[0].startswith("is ")


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


def test_retries_status_only_when_loading_messages_rejected():
    pass

    client = MagicMock()
    response = MagicMock()
    response.data = {
        "ok": False,
        "error": "invalid_arguments",
        "response_metadata": {
            "messages": ["[ERROR] must be less than 51 characters [json-pointer:/loading_messages/0]"]
        },
    }
    client.assistant_threads_setStatus.side_effect = [
        SlackApiError(message="invalid_arguments", response=response),
        {"ok": True},
    ]

    indicator = ThinkingIndicator(
        client,
        channel="C1",
        thread_ts="100.1",
        loading_messages=["Reading stack traces so you don't have to…"],
    )
    indicator.start()

    assert client.assistant_threads_setStatus.call_count == 2
    retry = client.assistant_threads_setStatus.call_args_list[1].kwargs
    assert "loading_messages" not in retry
    assert retry["status"].startswith("is ")
    assert "icon_emoji" not in retry


def test_legacy_fallback_when_assistant_unavailable():
    client = MagicMock()
    client.assistant_threads_setStatus.side_effect = Exception("missing_scope")
    client.chat_postMessage.return_value = {"ts": "888"}

    indicator = ThinkingIndicator(client, channel="C1", thread_ts="100.1")
    indicator.start()
    client.chat_postMessage.assert_called_once()

    indicator.finish("Done.")
    client.chat_delete.assert_called_once()
    assert client.chat_postMessage.call_count == 2
    assert client.chat_postMessage.call_args_list[-1].kwargs["text"] == "Done."


def test_legacy_rotation_updates_in_place(monkeypatch):
    client = MagicMock()
    client.chat_postMessage.return_value = {"ts": "888"}
    custom = [
        ":this_is_fine: Everything is fine. Checking prod…",
        ":rollsafe: Big brain debugging…",
    ]

    indicator = ThinkingIndicator(
        client,
        channel="C1",
        thread_ts="100.1",
        loading_messages=custom,
        rotation_seconds=0.01,
    )
    waits = iter([False, True])

    monkeypatch.setattr(indicator._stop_rotation, "wait", lambda _seconds: next(waits, True))
    indicator.start()
    indicator._rotation_thread.join(timeout=1.0)

    client.chat_update.assert_called_once()
    assert client.chat_update.call_args.kwargs["ts"] == "888"
    assert ":rollsafe:" in client.chat_update.call_args.kwargs["text"]
    client.chat_delete.assert_not_called()
