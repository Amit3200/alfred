"""Tests for Slack channel + thread context fetching."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from backend.orchestrator.policy import needs_context_refresh, wants_channel_history
from backend.integrations.slack.context import fetch_slack_context, parse_history_window
from backend.formatting.slack_messages import extract_message_text
from backend.models.task import Task


def test_wants_channel_history_on_yesterday_from_thread():
    assert wants_channel_history("was there any activity yesterday?", in_existing_thread=True)


def test_lookup_fetches_channel_in_thread():
    assert wants_channel_history(
        "when was the last event posted?",
        in_existing_thread=True,
    )


def test_correction_refreshes_context():
    assert needs_context_refresh("oops I meant something else", has_session=True)


def test_history_lookup_uses_30_day_window():
    now = datetime(2026, 6, 21, 12, 0, tzinfo=timezone.utc)
    _, _, label, limit = parse_history_window(
        "when was the last event posted?",
        now=now,
    )
    assert label == "last 30 days"
    assert limit == 200


def test_parse_history_window_yesterday():
    now = datetime(2026, 6, 21, 12, 0, tzinfo=timezone.utc)
    oldest, latest, label, limit = parse_history_window("alert yesterday?", now=now)
    assert label == "yesterday (UTC)"
    assert float(latest) > float(oldest)
    assert limit == 200


def test_extract_message_text_from_attachment_fields():
    message = {
        "username": "AlertsBot",
        "bot_id": "B1",
        "attachments": [
            {
                "pretext": "Closed: System: CPU (User) % has gone above 85 in Production in AcmeApp",
                "fields": [
                    {"title": "Severity", "value": "ERROR"},
                    {"title": "Current Value", "value": "29.3"},
                ],
            }
        ],
    }
    text = extract_message_text(message)
    assert "AcmeApp" in text
    assert "CPU" in text
    assert "Severity: ERROR" in text


def test_ticket_followup_in_thread_refreshes_context():
    assert needs_context_refresh("are you able to read the severity now?", has_session=True)


def test_ticket_followup_in_thread_fetches_channel():
    assert wants_channel_history(
        "are you able to read the severity now?",
        in_existing_thread=True,
    )


def test_fetch_slack_context_includes_channel_and_thread():
    client = MagicMock()
    client.conversations_history.return_value = {
        "ok": True,
        "messages": [
            {
                "ts": "1718860800.000000",
                "username": "AlertsBot",
                "bot_id": "B1",
                "text": "System status update in Production",
            }
        ],
    }
    client.conversations_replies.return_value = {
        "ok": True,
        "messages": [{"ts": "1718860900.000000", "user": "U1", "text": "was there an update?"}],
    }

    task = Task(
        source="slack",
        user_id="U1",
        channel_id="C1",
        thread_ts="1718860900.000000",
        raw_text="@alfred was there any activity yesterday?",
        cleaned_intent="was there any activity yesterday?",
        metadata={"in_existing_thread": True},
    )

    context = fetch_slack_context(client, task)
    assert context.text is not None
    assert "Channel messages" in context.text
    assert "Thread messages" in context.text
    assert "AlertsBot (app)" in context.text
    assert "status update" in context.text
    client.conversations_history.assert_called_once()
