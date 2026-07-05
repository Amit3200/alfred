"""Tests for context fetch policy."""

from backend.orchestrator.policy import (
    is_identity_question,
    needs_context_refresh,
    wants_channel_history,
)
from backend.formatting.slack_messages import format_slack_message


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


def test_prune_context_stack_traces():
    from backend.orchestrator.policy import prune_context

    tb = (
        "Traceback (most recent call last):\n"
        "  File \"app.py\", line 10, in main\n"
        "    run()\n"
        "  File \"app.py\", line 15, in run\n"
        "    execute()\n"
        "  File \"app.py\", line 20, in execute\n"
        "    do_work()\n"
        "  File \"app.py\", line 25, in do_work\n"
        "    raise ValueError(\"nested error\")\n"
        "ValueError: nested error"
    )
    result = prune_context(tb)
    assert "[Stack trace truncated for LLM readability]" in result
    assert "Traceback (most recent call last):" in result
    assert "ValueError: nested error" in result


def test_prune_context_long_urls():
    from backend.orchestrator.policy import prune_context

    long_url = "https://github.com/some-org/some-repo/pull/123/files?utf8=%E2%9C%93&src=pr&ref=main&auth=true&extra_param=very_long_extra_query_parameter_value_to_bloat_url"
    result = prune_context(f"Please check this URL: {long_url}")
    assert "[URL truncated]" in result
    assert "https://github.com/some-org/some-repo/pull/123/files" in result
