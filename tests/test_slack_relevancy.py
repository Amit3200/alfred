"""Tests for Slack thread relevancy ranking."""

from __future__ import annotations

from backend.integrations.slack.relevancy import (
    format_ranked_thread_section,
    rank_thread_messages,
    score_thread_message,
)


def _messages(count: int) -> list[dict]:
    return [{"user": "U1", "text": f"noise message number {index}"} for index in range(count)]


def test_score_prefers_stack_trace_and_intent_overlap():
    intent = "checkout handler order_id null pointer exception"
    trace = {
        "user": "U2",
        "text": "Traceback (most recent call last):\n  File src/checkout/handler.py:42\nKeyError: order_id",
    }
    noise = {"user": "U3", "text": "thanks for looking into this"}
    assert score_thread_message(trace, intent=intent, index=1, total=3) > score_thread_message(
        noise,
        intent=intent,
        index=2,
        total=3,
    )


def test_rank_thread_messages_keeps_top_n_in_order():
    messages = _messages(20)
    messages[18] = {
        "user": "U1",
        "text": "NullPointerException in checkout handler when order_id missing",
    }
    kept, omitted = rank_thread_messages(
        messages,
        "order_id missing checkout handler",
        requesting_user_id="U1",
        top_n=5,
    )
    assert len(kept) == 5
    assert len(omitted) == 15
    kept_text = " ".join(message.get("text", "") for message in kept)
    assert "order_id" in kept_text


def test_format_ranked_thread_section_includes_omission_summary():
    kept = [{"user": "U1", "text": "NullPointerException order_id missing in checkout handler"}]
    omitted = [{"user": "U2", "text": "older unrelated chatter about lunch plans today"}]
    text = format_ranked_thread_section(kept, omitted)
    assert text
    assert "order_id" in text
    assert "omitted" in text.lower()
