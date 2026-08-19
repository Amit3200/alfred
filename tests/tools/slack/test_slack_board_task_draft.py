"""Tests for Slack board task drafting and assignee/title parsing."""

from __future__ import annotations

from backend.routing.slack_board.intent import (
    extract_board_create_assignee,
    extract_task_title,
    is_weak_board_task_title,
)
from backend.routing.slack_board.task_draft import _parse_draft_json


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
    from backend.routing.slack_board.intent import infer_thread_action_assignee

    thread = (
        "<@URIYA|Riya Verma> please share the partnership sheet with "
        "<@UADITYA|Aditya Shaiwal> where he can check all the client names"
    )
    assert infer_thread_action_assignee(thread, bot_user_id="UBOT") == "URIYA"


def test_infer_thread_action_assignee_from_messages():
    from backend.routing.slack_board.intent import infer_thread_action_assignee_from_messages

    messages = [
        {
            "user": "UARNOLD",
            "text": (
                "<@URIYA|Riya Verma> please share the partnership sheet with "
                "<@UADITYA|Aditya Shaiwal> where he can check all the client names"
            ),
        }
    ]
    assert infer_thread_action_assignee_from_messages(messages, bot_user_id="UBOT") == "URIYA"


def test_format_board_thread_messages_keeps_mentions():
    from backend.routing.slack_board.intent import format_board_thread_messages

    messages = [
        {
            "user": "UARNOLD",
            "ts": "1733934420.000100",
            "text": (
                "<@URIYA|Riya Verma> please share the partnership sheet with "
                "<@UADITYA|Aditya Shaiwal>"
            ),
        }
    ]
    labels = {"UARNOLD": "Arnold", "URIYA": "Riya Verma", "UADITYA": "Aditya Shaiwal"}
    text = format_board_thread_messages(messages, mention_labels=labels)
    assert "@Riya Verma please share" in text
    assert "@Aditya Shaiwal" in text
    assert "<@URIYA" not in text


def test_finalize_skips_requester_when_thread_context():
    from backend.routing.slack_board.intent import finalize_board_create_fields

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
    from backend.routing.slack_board.intent import finalize_board_create_fields

    fields = finalize_board_create_fields(
        severity="",
        assignee_user_id="",
        requester_user_id="UREQUESTER",
        bot_user_id="UBOT",
    )
    assert fields["severity"] == "Medium"
    assert fields["assignee_user_id"] == "UREQUESTER"


def test_finalize_board_create_keeps_explicit_assignee_and_severity():
    from backend.routing.slack_board.intent import finalize_board_create_fields

    fields = finalize_board_create_fields(
        severity="p0",
        assignee_user_id="UARNOLD",
        requester_user_id="UREQUESTER",
        bot_user_id="UBOT",
    )
    assert fields["severity"] == "High"
    assert fields["assignee_user_id"] == "UARNOLD"


def test_extract_title_from_summary():
    from backend.routing.slack_board.intent import extract_title_from_summary

    desc = "Summary: Share partnership sheet with Aditya\nSlack thread: https://slack.com/..."
    assert extract_title_from_summary(desc) == "Share partnership sheet with Aditya"
    assert extract_title_from_summary("Summary: the above?\nContext:") == ""


def test_build_details_skips_weak_task_title():
    from backend.routing.slack_board.intent import build_board_task_details

    body = build_board_task_details(
        messages_text="[1] arnold: please share the partnership sheet with Aditya",
        task_title="the above?",
    )
    assert "Summary: the above?" not in body
    assert "partnership sheet" in body.lower()


def test_humanize_board_task_text():
    from backend.routing.slack_board.intent import humanize_board_task_text

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


def test_parse_batch_draft_rows():
    from backend.routing.slack_board.task_draft import _parse_batch_task_rows

    content = """{
      "tasks": [
        {"source_title": "Snapchat Integration", "title": "Add Snapchat integration", "description": "Summary: Add Snapchat integration"},
        {"source_title": "UPI Intent", "title": "Enable UPI Intent", "description": "Summary: Enable UPI Intent for Mishmash and Everaw"}
      ]
    }"""
    rows = _parse_batch_task_rows(content)
    assert len(rows) == 2
    assert rows[0]["title"] == "Add Snapchat integration"


def test_batch_draft_fallback_without_llm():
    from unittest.mock import patch

    from backend.models.config import AlfredConfig
    from backend.models.task import Task
    from backend.routing.slack_board.task_draft import draft_board_tasks_batch_from_thread

    task = Task(
        source="slack",
        user_id="U1",
        channel_id="C1",
        raw_text="create a task for all the above issues",
        cleaned_intent="create a task for all the above issues",
    )
    with patch(
        "backend.routing.slack_board.task_draft.LLMRouter.from_config",
        side_effect=RuntimeError("no llm"),
    ):
        drafts = draft_board_tasks_batch_from_thread(
            config=AlfredConfig(),
            task=task,
            item_titles=["Exit reason to be given on Export file", "Snapchat Integration"],
            thread_url="https://slack.example/thread",
            mention_labels={"U1": "Azeem"},
            default_severity="Medium",
        )
    assert len(drafts) == 2
    assert drafts[0].title == "Exit reason to be given on Export file"
    assert "Summary: Snapchat Integration" in drafts[1].description
    assert "Exit reason" not in drafts[1].description
    assert "Requested by: @Azeem" in drafts[0].description


def test_batch_draft_uses_llm_per_item_descriptions():
    from unittest.mock import MagicMock, patch

    from backend.ai.base import LLMResponse
    from backend.models.config import AlfredConfig
    from backend.models.task import Task
    from backend.routing.slack_board.task_draft import draft_board_tasks_batch_from_thread

    task = Task(
        source="slack",
        user_id="U1",
        channel_id="C1",
        raw_text="create a task for all the above issues",
        cleaned_intent="create a task for all the above issues",
    )
    provider = MagicMock()
    provider.chat.return_value = LLMResponse(
        content="""{
          "tasks": [
            {
              "source_title": "Exit reason to be given on Export file",
              "title": "Add exit reason to export file",
              "description": "Summary: Add the exit reason field on export files.\\nRequested by: @Azeem",
              "assignee_user_id": "",
              "severity": "Medium"
            },
            {
              "source_title": "Snapchat Integration",
              "title": "Integrate Snapchat ads",
              "description": "Summary: Integrate Snapchat for ads tracking.\\nRequested by: @Azeem",
              "assignee_user_id": "",
              "severity": "Low"
            }
          ]
        }"""
    )
    router = MagicMock()
    with patch(
        "backend.routing.slack_board.task_draft.LLMRouter.from_config",
        return_value=router,
    ), patch(
        "backend.ai.routing.resolve_llm_route",
        return_value=("openai", provider, "test-model"),
    ):
        drafts = draft_board_tasks_batch_from_thread(
            config=AlfredConfig(),
            task=task,
            item_titles=["Exit reason to be given on Export file", "Snapchat Integration"],
            mention_labels={"U1": "Azeem"},
            default_severity="Medium",
        )
    assert [d.title for d in drafts] == [
        "Add exit reason to export file",
        "Integrate Snapchat ads",
    ]
    assert "exit reason field" in drafts[0].description.lower()
    assert "Snapchat" in drafts[1].description
    assert "exit reason field" not in drafts[1].description.lower()
    assert drafts[1].severity == "Low"
