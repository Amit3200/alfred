"""Tests for Slack board intent parsing."""

from __future__ import annotations

from backend.routing.slack_board_intent import (
    extract_severity_target,
    extract_task_title,
    extract_ticket_ref,
    looks_like_slack_board_create,
    looks_like_slack_board_request,
    looks_like_slack_board_update,
    references_thread_context,
    resolve_ticket_ref,
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
    assert looks_like_slack_board_update(intent)
    assert extract_ticket_ref(intent) == "TS-42"


def test_update_detects_assign_this_task():
    intent = "assign this task to @user"
    assert looks_like_slack_board_update(intent)
    assert not looks_like_slack_board_create(intent)


def test_update_detects_st_prefix_inline_status():
    intent = "ST-1 is in progress and assign severity to High. Also assign it to @user"
    assert looks_like_slack_board_update(intent)
    assert extract_ticket_ref(intent) == "ST-1"


def test_update_detects_slack_board_context():
    intent = "Update (slack board sales-tracker) ST-1 is in progress"
    assert looks_like_slack_board_update(intent)
    assert extract_ticket_ref(intent) == "ST-1"


def test_display_prefix_update_not_board_task_update():
    intent = "update the Display Prefix to ST"
    assert not looks_like_slack_board_update(intent)


def test_extract_severity_target():
    intent = "ST-1 is in progress and assign severity to High"
    assert extract_severity_target(intent) == "High"


def test_resolve_ticket_ref_from_session():
    ref = resolve_ticket_ref(
        "assign this task to @user",
        session_metadata={"last_board_task": {"display_id": "TS-9", "record_id": "Rec1"}},
    )
    assert ref == "TS-9"
