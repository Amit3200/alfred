"""Precedence when a create-task intent could match Slack Lists or JIRA."""

from __future__ import annotations

import re
from typing import Any

_CREATE_VERB_RE = re.compile(
    r"\b(?:create|add|file|raise|open|log|submit)\b",
    re.I,
)
_CREATE_NOUN_RE = re.compile(
    r"\b(?:task|ticket|item|issue|bug)\b",
    re.I,
)
_EXPLICIT_JIRA_RE = re.compile(r"\bjira(?:\s+(?:board|dashboard|project))?\b", re.I)
_EXPLICIT_SLACK_LIST_RE = re.compile(
    r"\b(?:slack\s+list|slack\s+board|bugs?\s*tracker|on\s+(?:the\s+)?list\s+board)\b",
    re.I,
)
_JIRA_THREAD_MARKERS = (
    "jira_create_issue",
    "jira dashboard",
    "jira board",
    "tech board",
    "project key",
    "governance:",
    "requires explicit approval",
)
_PERSONA_SKIP_JIRA_RE = re.compile(
    r"\b(?:do not|don't|never|not)\b.{0,48}\b(?:create|open|file|raise).{0,48}\bjira\b"
    r"|\bjira\b.{0,48}\b(?:do not|don't|never)\s+create\b",
    re.I,
)


def _ticket_target(session_metadata: dict[str, Any] | None) -> str:
    return str((session_metadata or {}).get("ticket_create_target") or "").strip().lower()


def _looks_like_create_request(text: str) -> bool:
    return bool(_CREATE_VERB_RE.search(text) and _CREATE_NOUN_RE.search(text))


def persona_prefers_jira_creates(persona: str) -> bool:
    """True when the channel persona instructs Alfred to create in JIRA."""
    text = (persona or "").strip()
    if not text:
        return False
    lower = text.lower()
    if _PERSONA_SKIP_JIRA_RE.search(lower):
        return False
    if "jira_create_issue" in lower:
        return True
    if "jira" not in lower:
        return False
    if re.search(r"\b(?:create|open|file|raise)\b.{0,160}\bjira\b", lower):
        return True
    if re.search(r"\bjira\b.{0,160}\b(?:create|open|file|raise)\b", lower):
        return True
    if "tech board" in lower:
        return True
    if re.search(r"project(?:\s+key)?\s*[`:]\s*tech\b", lower):
        return True
    return False


def channel_prefers_jira_creates(
    *,
    channel_id: str = "",
    data_dir: Any = None,
    session_metadata: dict[str, Any] | None = None,
) -> bool:
    """True when this Slack channel should create in JIRA.

    Slack List remains the default. A JIRA-oriented channel persona or an
    explicit channel workflow of ``jira`` overrides that default.
    """
    target = _ticket_target(session_metadata)
    if target == "jira":
        return True
    # Button/session choice of Slack List wins over persona for that turn.
    if target in ("slack_list", "slack", "list", "board"):
        return False
    cid = (channel_id or "").strip()
    if not cid:
        return False
    from backend.integrations.slack.workflow_registry import channel_ticket_system, resolve_data_dir
    from backend.routing.channel_settings import channel_persona_prompt

    dd = resolve_data_dir(data_dir)
    if persona_prefers_jira_creates(channel_persona_prompt(dd, cid)):
        return True
    return channel_ticket_system(cid, data_dir=dd) == "jira"


def should_route_create_to_jira(
    intent: str,
    *,
    jira_enabled: bool = True,
    session_turns: tuple[str, ...] = (),
    session_metadata: dict[str, Any] | None = None,
    thread_context: str = "",
    channel_id: str = "",
    data_dir: Any = None,
) -> bool:
    """True when create intent should use JIRA, not Slack List direct handlers."""
    if not jira_enabled:
        return False

    text = (intent or "").strip()
    if not text:
        return False

    from backend.routing.jira.intent import (
        looks_like_jira_create_followup,
        looks_like_jira_create_request,
    )

    if _EXPLICIT_SLACK_LIST_RE.search(text) and not _EXPLICIT_JIRA_RE.search(text):
        return False

    meta = session_metadata or {}
    target = _ticket_target(meta)
    if target == "jira":
        return True

    if channel_prefers_jira_creates(
        channel_id=channel_id,
        data_dir=data_dir,
        session_metadata=meta,
    ) and _looks_like_create_request(text):
        from backend.routing.slack_board.intent import looks_like_batch_board_create

        if not looks_like_batch_board_create(text):
            return True

    # Slack List language wins unless the user named JIRA. Otherwise a prior
    # failed jira_create_issue in the thread poisons later "create tasks" asks.
    if not _EXPLICIT_JIRA_RE.search(text):
        from backend.routing.slack_board.intent import looks_like_batch_board_create

        if looks_like_batch_board_create(text):
            return False
        if re.search(r"\b(?:create|add|open|file)\b.{0,48}\b(?:a\s+)?tasks?\b", text, re.I):
            return False

    if looks_like_jira_create_request(text):
        return True
    if looks_like_jira_create_followup(
        text,
        session_turns=session_turns,
        thread_context=thread_context,
    ):
        return True

    if _EXPLICIT_JIRA_RE.search(text) and _CREATE_VERB_RE.search(text):
        return True
    if _EXPLICIT_JIRA_RE.search(text) and _CREATE_NOUN_RE.search(text) and _CREATE_VERB_RE.search(text):
        return True
    if re.search(r"\b(?:create|add)\b.{0,80}\b(?:task|ticket)\b.{0,80}\bjira\b", text, re.I):
        return True

    combined = "\n".join([*session_turns[-8:], thread_context or "", text]).lower()
    if "jira" in combined and _CREATE_VERB_RE.search(text):
        if sum(1 for marker in _JIRA_THREAD_MARKERS if marker in combined) >= 1:
            return True
        if re.search(r"\btech\s+board\b", combined) and "jira" in combined:
            return True

    return False
