"""Tests for Slack board intent parsing."""

from __future__ import annotations

from backend.routing.slack_board_intent import (
    extract_task_title,
    extract_ticket_ref,
    looks_like_slack_board_create,
    looks_like_slack_board_request,
    references_thread_context,
)


def test_create_task_for_above_title():
    intent = "create task for payment timeout on checkout for above"
    assert looks_like_slack_board_create(intent)
    assert references_thread_context(intent)
    assert extract_task_title(intent) == "payment timeout on checkout"


def test_create_task_on_title():
    intent = "create a task on working on the revamping the AI as p0"
    assert looks_like_slack_board_create(intent)
    assert "revamping" in extract_task_title(intent).lower()


def test_create_task_simple():
    assert looks_like_slack_board_create("please create task for merchant sync failure")
    assert extract_task_title("create task for merchant sync failure") == "merchant sync failure"


def test_board_request_and_ticket_ref():
    intent = "move TS-42 to in progress"
    assert looks_like_slack_board_request(intent)
    assert extract_ticket_ref(intent) == "TS-42"
