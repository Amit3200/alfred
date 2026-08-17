"""Tests for JIRA vs Slack List create disambiguation."""

from __future__ import annotations

from backend.models.config import (
    AlfredConfig,
    JiraConfig,
    SlackBoardProfile,
    SlackBoardWorkflowsConfig,
    SlackConfig,
)
from backend.models.task import Task
from backend.routing.ticket_create_disambiguation import (
    build_disambiguation_response,
    is_generic_ticket_create_intent,
    needs_ticket_create_disambiguation,
    resolve_target_from_pending_reply,
    slack_blocks_from_response,
)


def _dual_config() -> AlfredConfig:
    return AlfredConfig(
        jira=JiraConfig(enabled=True),
        slack=SlackConfig(
            enabled=True,
            board_workflows=SlackBoardWorkflowsConfig(
                enabled=True,
                boards=[
                    SlackBoardProfile(
                        name="bugs",
                        list_id="F001",
                        channel_ids=["Ctech"],
                    )
                ],
            ),
        ),
    )


def test_generic_create_is_ambiguous_in_dual_channel():
    config = _dual_config()
    task = Task(
        source="slack",
        user_id="U1",
        channel_id="Ctech",
        thread_ts="1.2",
        raw_text="create ticket for checkout error for above",
        cleaned_intent="create ticket for checkout error for above",
    )
    assert is_generic_ticket_create_intent(task.cleaned_intent)
    assert needs_ticket_create_disambiguation(task, config)


def test_explicit_jira_skips_disambiguation():
    config = _dual_config()
    task = Task(
        source="slack",
        user_id="U1",
        channel_id="Ctech",
        thread_ts="1.2",
        raw_text="create jira ticket for checkout",
        cleaned_intent="create jira ticket for checkout",
    )
    assert not is_generic_ticket_create_intent(task.cleaned_intent)
    assert not needs_ticket_create_disambiguation(task, config)


def test_disambiguation_response_has_buttons():
    response = build_disambiguation_response(session_key="slack:C1:1.2")
    blocks = slack_blocks_from_response(response)
    assert blocks
    actions = next(b for b in blocks if b.get("type") == "actions")
    ids = {el.get("action_id") for el in actions.get("elements", [])}
    assert ids == {"ticket_create_slack", "ticket_create_jira"}


def test_text_reply_resolves_pending():
    class Session:
        metadata = {
            "pending_ticket_create": {
                "intent": "create ticket for foo",
                "raw_text": "create ticket for foo",
                "user_id": "U1",
                "created_at": 9999999999,
            }
        }

    task = Task(
        source="slack",
        user_id="U1",
        channel_id="C1",
        thread_ts="1.2",
        raw_text="slack",
        cleaned_intent="slack",
    )
    assert resolve_target_from_pending_reply(task, Session()) == "slack_list"
