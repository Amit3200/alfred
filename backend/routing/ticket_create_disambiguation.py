"""Disambiguate generic ticket/task create between Slack Lists and JIRA."""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Literal

from backend.models.config import AlfredConfig
from backend.models.response import AssistantResponse, ResponsePayload
from backend.models.task import Task

logger = logging.getLogger(__name__)

TicketCreateTarget = Literal["slack_list", "jira"]

_PENDING_KEY = "pending_ticket_create"
_TARGET_KEY = "ticket_create_target"
_PENDING_TTL_SECONDS = 30 * 60

_GENERIC_CREATE_RE = re.compile(
    r"\b(?:create|add|open|file|raise|log|submit)\b.{0,24}\b(?:task|ticket|item|bug)\b",
    re.I,
)
_EXPLICIT_JIRA_RE = re.compile(r"\bjira\b", re.I)
_EXPLICIT_BOARD_RE = re.compile(
    r"\b(?:slack\s+list|bugs?\s*tracker|on\s+(?:the\s+)?board|slack\s+board|list\s+board)\b",
    re.I,
)
_SLACK_CHOICE_RE = re.compile(
    r"^(?:slack(?:\s+list)?|list|board|bugs?\s*tracker|on\s+board)\.?$",
    re.I,
)
_JIRA_CHOICE_RE = re.compile(r"^(?:jira|atlassian)\.?$", re.I)


def is_generic_ticket_create_intent(intent: str) -> bool:
    text = (intent or "").strip()
    if not text or not _GENERIC_CREATE_RE.search(text):
        return False
    if _EXPLICIT_JIRA_RE.search(text):
        return False
    if _EXPLICIT_BOARD_RE.search(text):
        return False
    return True


def ticket_create_target_from_task(task: Task) -> TicketCreateTarget | None:
    raw = str(task.metadata.get(_TARGET_KEY) or "").strip().lower()
    if raw in ("slack_list", "slack", "list", "board"):
        return "slack_list"
    if raw == "jira":
        return "jira"
    return None


def _pending_valid(pending: dict[str, Any] | None) -> bool:
    if not isinstance(pending, dict):
        return False
    created = float(pending.get("created_at") or 0)
    if created and time.time() - created > _PENDING_TTL_SECONDS:
        return False
    return bool(str(pending.get("intent") or "").strip())


def resolve_target_from_pending_reply(task: Task, session: Any | None) -> TicketCreateTarget | None:
    """Resolve Slack/JIRA from a short reply while disambiguation is pending."""
    if session is None:
        return None
    pending = session.metadata.get(_PENDING_KEY)
    if not _pending_valid(pending):
        return None
    text = (task.cleaned_intent or "").strip()
    if _SLACK_CHOICE_RE.match(text):
        return "slack_list"
    if _JIRA_CHOICE_RE.match(text):
        return "jira"
    return None


def needs_ticket_create_disambiguation(
    task: Task,
    config: AlfredConfig,
    *,
    session: Any | None = None,
    data_dir: Any = None,
) -> bool:
    if task.source != "slack":
        return False
    if not config.slack.ticket_create_disambiguation:
        return False
    if ticket_create_target_from_task(task):
        return False
    if session and resolve_target_from_pending_reply(task, session):
        return False
    if not is_generic_ticket_create_intent(task.cleaned_intent):
        return False

    from backend.domains.slack_board.operations import board_enabled, resolve_board_for_task
    from backend.integrations.slack.workflow_registry import channel_ticket_system, resolve_data_dir

    dd = resolve_data_dir(data_dir)
    board_ok = board_enabled(config, dd) and resolve_board_for_task(config, task, data_dir=dd) is not None
    jira_ok = bool(config.jira.enabled)
    if not (board_ok and jira_ok):
        return False

    policy = channel_ticket_system(task.channel_id or "", data_dir=dd)
    if policy == "slack_list":
        return False
    if policy == "jira":
        return False
    return True


def default_ticket_create_target(
    task: Task,
    config: AlfredConfig,
    *,
    data_dir: Any = None,
) -> TicketCreateTarget | None:
    """Channel DB policy when user did not choose explicitly."""
    from backend.integrations.slack.workflow_registry import channel_ticket_system, resolve_data_dir

    cid = task.channel_id or ""
    dd = resolve_data_dir(data_dir)
    from backend.routing.create_target_precedence import channel_prefers_jira_creates

    if channel_prefers_jira_creates(channel_id=cid, data_dir=dd):
        return "jira"
    policy = channel_ticket_system(cid, data_dir=dd)
    if policy == "slack_list":
        return "slack_list"
    if policy == "jira":
        return "jira"
    return None


def store_pending_ticket_create(session: Any, task: Task) -> None:
    session.metadata[_PENDING_KEY] = {
        "intent": task.cleaned_intent,
        "raw_text": task.raw_text,
        "user_id": task.user_id,
        "created_at": time.time(),
    }


def clear_pending_ticket_create(session: Any) -> None:
    session.metadata.pop(_PENDING_KEY, None)


def apply_ticket_create_target(session: Any | None, target: TicketCreateTarget) -> None:
    if session is not None:
        session.metadata[_TARGET_KEY] = target
        clear_pending_ticket_create(session)


def build_disambiguation_response(*, session_key: str, intro: str | None = None) -> AssistantResponse:
    text = intro or (
        "I can create this on your **Slack List board** (Bugs tracker) or in **JIRA**. "
        "Which should I use?"
    )
    slack_value = encode_button_session_value(session_key, "slack_list")
    jira_value = encode_button_session_value(session_key, "jira")
    blocks = [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": text},
        },
        {
            "type": "actions",
            "block_id": "ticket_create_disambiguation",
            "elements": [
                {
                    "type": "button",
                    "action_id": "ticket_create_slack",
                    "text": {"type": "plain_text", "text": "Slack List", "emoji": True},
                    "style": "primary",
                    "value": slack_value,
                },
                {
                    "type": "button",
                    "action_id": "ticket_create_jira",
                    "text": {"type": "plain_text", "text": "JIRA", "emoji": True},
                    "value": jira_value,
                },
            ],
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "Or reply with `slack` or `jira` in this thread.",
                }
            ],
        },
    ]
    return AssistantResponse(
        payload=ResponsePayload(kind="text", data={"text": text, "slack_blocks": blocks}),
        text=text,
    )


def encode_button_session_value(session_key: str, target: TicketCreateTarget) -> str:
    return json.dumps({"session_key": session_key, "target": target}, separators=(",", ":"))


def decode_button_session_value(raw: str) -> tuple[str, TicketCreateTarget] | None:
    try:
        payload = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return None
    session_key = str(payload.get("session_key") or "").strip()
    target = str(payload.get("target") or "").strip().lower()
    if not session_key:
        return None
    if target in ("slack_list", "slack"):
        return session_key, "slack_list"
    if target == "jira":
        return session_key, "jira"
    return None


def task_from_pending_session(
    session: Any,
    *,
    channel_id: str,
    thread_ts: str,
    user_id: str,
    target: TicketCreateTarget,
) -> Task | None:
    pending = session.metadata.get(_PENDING_KEY)
    if not _pending_valid(pending):
        return None
    apply_ticket_create_target(session, target)
    return Task(
        source="slack",
        user_id=user_id or str(pending.get("user_id") or ""),
        channel_id=channel_id,
        thread_ts=thread_ts,
        raw_text=str(pending.get("raw_text") or ""),
        cleaned_intent=str(pending.get("intent") or ""),
        metadata={_TARGET_KEY: target},
    )


def slack_blocks_from_response(response: AssistantResponse) -> list[dict[str, Any]] | None:
    blocks = response.payload.data.get("slack_blocks")
    if isinstance(blocks, list) and blocks:
        return blocks
    return None
