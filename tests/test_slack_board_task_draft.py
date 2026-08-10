"""Tests for Slack board task drafting and assignee/title parsing."""

from __future__ import annotations

from backend.routing.slack_board_intent import (
    extract_board_create_assignee,
    extract_task_title,
    is_weak_board_task_title,
)
from backend.routing.slack_board_task_draft import _parse_draft_json


def test_weak_titles():
    assert is_weak_board_task_title("the same")
    assert is_weak_board_task_title("to call me")
    assert not is_weak_board_task_title("Review community replies for one-click checkout")


def test_create_on_assignee_not_cc():
    raw = (
        "@channel merchants enable checkout cc: <@USULTAN|sultan> <@UBOT|alfred> "
        "create a task on <@UARNOLD|Arnold> for the same"
    )
    assignee = extract_board_create_assignee(
        raw,
        bot_user_id="UBOT",
        requester_user_id="UAZEEM",
    )
    assert assignee == "UARNOLD"


def test_create_assignee_falls_back_to_cc():
    raw = (
        "@channel merchants enable checkout cc: <@USULTAN|sultan> <@UBOT|alfred> "
        "create a task for the same"
    )
    assignee = extract_board_create_assignee(
        raw,
        bot_user_id="UBOT",
        requester_user_id="UAZEEM",
    )
    assert assignee == "USULTAN"


def test_finalize_board_create_defaults():
    from backend.routing.slack_board_intent import finalize_board_create_fields

    fields = finalize_board_create_fields(
        severity="",
        assignee_user_id="",
        requester_user_id="UREQUESTER",
        bot_user_id="UBOT",
    )
    assert fields["severity"] == "Medium"
    assert fields["assignee_user_id"] == "UREQUESTER"


def test_finalize_board_create_keeps_explicit_assignee_and_severity():
    from backend.routing.slack_board_intent import finalize_board_create_fields

    fields = finalize_board_create_fields(
        severity="p0",
        assignee_user_id="UARNOLD",
        requester_user_id="UREQUESTER",
        bot_user_id="UBOT",
    )
    assert fields["severity"] == "High"
    assert fields["assignee_user_id"] == "UARNOLD"


def test_create_on_to_call_me_title_empty():
    cleaned = "create a task on  to call me"
    assert extract_task_title(cleaned) == ""


def test_parse_draft_json_codeblock():
    content = '''Here is the draft:
```json
{"title": "Call Azeem about pipeline", "description": "Summary: x", "assignee_user_id": "U1", "severity": "", "confidence": 0.9}
```'''
    parsed = _parse_draft_json(content)
    assert parsed is not None
    assert parsed["title"] == "Call Azeem about pipeline"
    assert parsed["confidence"] == 0.9
