"""Tests for Layer 1 ingress — sanitizer and processor."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from backend.ingress.processor import TaskProcessor
from backend.ingress.sanitize import channel_allowed, clean_slack_text, sanitize_slack_mention
from backend.models.config import SlackConfig, default_config
from backend.models.task import Task


def test_clean_slack_text_strips_mention_and_alfred_prefix():
    assert clean_slack_text("<@U123ABC> @alfred why is this broken?") == "why is this broken?"
    assert clean_slack_text("<@U123ABC> hello") == "hello"


def test_channel_allowed_wildcard():
    cfg = SlackConfig(allowed_channels=["*"])
    assert channel_allowed("C123", cfg) is True


def test_channel_allowed_specific_ids():
    cfg = SlackConfig(allowed_channels=["C111", "C222"])
    assert channel_allowed("C111", cfg) is True
    assert channel_allowed("C999", cfg) is False


def test_sanitize_slack_mention_builds_task():
    cfg = SlackConfig(allowed_channels=["*"])
    event = {
        "user": "U1",
        "channel": "C1",
        "ts": "1234.5678",
        "text": "<@UBOT> can you explain this error?",
    }
    task = sanitize_slack_mention(event, cfg)
    assert task is not None
    assert task.source == "slack"
    assert task.user_id == "U1"
    assert task.channel_id == "C1"
    assert task.thread_ts == "1234.5678"
    assert task.cleaned_intent == "can you explain this error?"


def test_sanitize_slack_mention_rejects_disallowed_channel():
    cfg = SlackConfig(allowed_channels=["C-other"])
    event = {"user": "U1", "channel": "C1", "ts": "1", "text": "<@B> hi"}
    assert sanitize_slack_mention(event, cfg) is None


def test_task_processor_calls_llm():
    config = default_config()
    mock_provider = MagicMock()
    mock_response = MagicMock()
    mock_response.content = "The bug is in auth.py line 42."
    mock_provider.chat.return_value = mock_response

    processor = TaskProcessor(config)
    processor.router = MagicMock()
    processor.router.get.return_value = mock_provider

    task = Task(
        source="cli",
        user_id="local",
        raw_text="why bug?",
        cleaned_intent="why bug?",
    )
    reply = processor.process(task)
    assert reply == "The bug is in auth.py line 42."
    mock_provider.chat.assert_called_once()


def test_slack_listener_ready_requires_socket_mode_tokens():
    from backend.slack.listener import slack_listener_ready

    config = default_config()
    config.slack.enabled = True
    ok, msg = slack_listener_ready(config)
    assert ok is False
    assert "xoxb" in msg or "bot token" in msg.lower()

    config.slack.bot_token = "xoxb-test"
    config.slack.signing_secret = "secret"
    ok, msg = slack_listener_ready(config)
    assert ok is False
    assert "xapp" in msg

    config.slack.app_token = "xapp-test"
    ok, _ = slack_listener_ready(config)
    assert ok is True
