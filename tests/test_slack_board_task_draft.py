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
    assert is_weak_board_task_title("the above?")
    assert is_weak_board_task_title("the above")
    assert not is_weak_board_task_title("Review community replies for one-click checkout")


def test_create_task_for_the_above_title_empty():
    assert extract_task_title("can you create the task for the above?") == ""
    assert extract_task_title("@alfred create the task for the above") == ""


def test_infer_thread_action_assignee():
    from backend.routing.slack_board_intent import infer_thread_action_assignee

    thread = (
        "<@URIYA|Riya Verma> please share the partnership sheet with "
        "<@UADITYA|Aditya Shaiwal> where he can check all the client names"
    )
    assert infer_thread_action_assignee(thread, bot_user_id="UBOT") == "URIYA"


def test_finalize_skips_requester_when_thread_context():
    from backend.routing.slack_board_intent import finalize_board_create_fields

    fields = finalize_board_create_fields(
        severity="",
        assignee_user_id="",
        requester_user_id="UREQUESTER",
        bot_user_id="UBOT",
        default_assignee_to_requester=False,
    )
    assert fields["severity"] == "Medium"
    assert fields["assignee_user_id"] == ""


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


def test_extract_title_from_summary():
    from backend.routing.slack_board_intent import extract_title_from_summary

    desc = "Summary: Share partnership sheet with Aditya\nSlack thread: https://slack.com/..."
    assert extract_title_from_summary(desc) == "Share partnership sheet with Aditya"
    assert extract_title_from_summary("Summary: the above?\nContext:") == ""


def test_build_details_skips_weak_task_title():
    from backend.routing.slack_board_intent import build_board_task_details

    body = build_board_task_details(
        messages_text="[1] arnold: please share the partnership sheet with Aditya",
        task_title="the above?",
    )
    assert "Summary: the above?" not in body
    assert "partnership sheet" in body.lower()


def test_humanize_board_task_text():
    from backend.routing.slack_board_intent import humanize_board_task_text

    text = "Requested by: U0522NX5GG0\nContext:\n• U08GJJVK3UL asked for access"
    labels = {"U0522NX5GG0": "Amit Singh Sansoya", "U08GJJVK3UL": "Arnold"}
    out = humanize_board_task_text(text, labels)
    assert "@Amit Singh Sansoya" in out
    assert "@Arnold" in out
    assert "U0522NX5GG0" not in out


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
