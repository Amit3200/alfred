"""Tests for context fetch policy."""

from backend.ingress.context_policy import (
    is_identity_question,
    needs_context_refresh,
    wants_channel_history,
)
from backend.ingress.slack_messages import format_slack_message


def test_identity_skips_channel_history():
    assert is_identity_question("who are you exactly?")
    assert wants_channel_history("who are you exactly?", in_existing_thread=True) is False


def test_try_again_refreshes_context():
    assert needs_context_refresh("can you try again?", has_session=True) is True


def test_thread_follow_up_without_refresh():
    assert needs_context_refresh("thanks", has_session=True) is False


def test_lookup_refreshes_context():
    assert needs_context_refresh("when was the last event posted?", has_session=True)


def test_tell_me_again_refreshes_context():
    assert needs_context_refresh("can you tell me this again?", has_session=True)


def test_correction_refreshes_context():
    assert needs_context_refresh("oops I meant the other thread", has_session=True)


def test_summary_fetches_channel_in_thread():
    assert wants_channel_history(
        "can you summarize this thread for June?",
        in_existing_thread=True,
    )


def test_reactions_in_message_format():
    msg = {
        "username": "AlertsBot",
        "bot_id": "B1",
        "ts": "1780000000.0",
        "text": "Example alert message",
        "reactions": [{"name": "white_check_mark", "count": 1, "users": ["UACK123"]}],
    }
    line = format_slack_message(msg, user_names={"UACK123": "Alex"})
    assert line is not None
    assert "white_check_mark" in line
    assert "Alex" in line
    assert "UACK123" not in line
