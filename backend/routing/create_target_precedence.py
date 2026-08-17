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
_JIRA_THREAD_MARKERS = (
    "jira_create_issue",
    "jira dashboard",
    "jira board",
    "tech board",
    "project key",
    "governance:",
    "requires explicit approval",
)


def should_route_create_to_jira(
    intent: str,
    *,
    jira_enabled: bool = True,
    session_turns: tuple[str, ...] = (),
    session_metadata: dict[str, Any] | None = None,
    thread_context: str = "",
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

    if looks_like_jira_create_request(text):
        return True
    if looks_like_jira_create_followup(
        text,
        session_turns=session_turns,
        thread_context=thread_context,
    ):
        return True

    meta = session_metadata or {}
    target = str(meta.get("ticket_create_target") or "").strip().lower()
    if target == "jira":
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
