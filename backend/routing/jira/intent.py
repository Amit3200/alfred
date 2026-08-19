"""JIRA create-intent detection — kept separate to avoid routing import cycles."""

from __future__ import annotations

import re

_CREATE_JIRA_RE = re.compile(
    r"\b(?:create|file|raise|open|log|submit|add)\b.*\b(?:jira|issue|ticket|bug)\b"
    r"|\b(?:jira|issue|ticket|bug)\b.*\b(?:create|file|raise|open|log|submit|add)\b"
    r"|\b(?:create|add|file|raise|open|log|submit)\b.{0,80}\b(?:task|ticket)\b.{0,80}\bjira\b",
    re.I,
)

_CREATE_JIRA_REFERENCE_RE = re.compile(
    r"\b(?:create|file|raise|open|log|submit|add)\b.{0,40}\b(?:above|this|that|the)\s+(?:ticket|issue|bug)\b"
    r"|\b(?:create|file|raise|open|log|submit)\b.{0,20}\b(?:above|these|them|those|it)\b",
    re.I,
)
_SLACK_TASK_CREATE_RE = re.compile(
    r"\b(?:create|add|open|file)\b.{0,48}\b(?:a\s+)?tasks?\b",
    re.I,
)

_PROJECT_KEY_HINT_RE = re.compile(
    r"\b(?:project\s+key|use|remember|always)\b.{0,40}\b(?:TS|TECH)\b"
    r"|\b(?:TS|TECH)\b\s*(?:board|project)\b"
    r"|\b(?:not|isn't|is not)\s+TECH-SUPPORT\b",
    re.I,
)

_CREATE_ON_BOARD_RE = re.compile(
    r"\b(?:above|these|them|those|it|one)\b.{0,40}\b(?:on|in|to)\b.{0,20}\b(?:TS|board|jira)\b",
    re.I,
)

_JIRA_CREATE_CONTEXT_MARKERS = (
    "create",
    "jira",
    "ticket",
    "ts board",
    "tech-support",
    "not picked",
    "submit a ticket",
    "project key",
    "merchant",
    "severity",
    "summary",
    "jira_create",
    "integration with",
)


_ASSIGN_RE = re.compile(
    r"\bassign\b.{0,60}\b(ticket|issue|jira|PROJ|\w+-\d+)",
    re.I,
)
_TRANSITION_RE = re.compile(
    r"\b(move|transition|change\s+status|mark)\b.{0,40}\b(done|closed|resolved|in\s+progress|review)\b",
    re.I,
)


def looks_like_jira_create_request(intent: str) -> bool:
    """True when the user wants a new JIRA issue, not identity lookup."""
    text = intent or ""
    if not text:
        return False
    # "@alfred create a task for all the above issues" is Slack List language.
    # The "create … above" JIRA follow-up regex must not steal it unless JIRA is explicit.
    if _SLACK_TASK_CREATE_RE.search(text) and not re.search(r"\bjira\b", text, re.I):
        return False
    return bool(_CREATE_JIRA_RE.search(text) or _CREATE_JIRA_REFERENCE_RE.search(text))


def looks_like_jira_assign_request(intent: str) -> bool:
    return bool(_ASSIGN_RE.search(intent or ""))


def looks_like_jira_transition_request(intent: str) -> bool:
    return bool(_TRANSITION_RE.search(intent or ""))


def _thread_has_jira_create_context(text: str) -> bool:
    lower = (text or "").lower()
    return sum(1 for marker in _JIRA_CREATE_CONTEXT_MARKERS if marker in lower) >= 2


def looks_like_jira_create_followup(
    intent: str,
    *,
    session_turns: tuple[str, ...] = (),
    thread_context: str | None = None,
) -> bool:
    """Thread follow-up to create JIRA from ticket context (may omit 'ticket' / 'create')."""
    if looks_like_jira_create_request(intent):
        return True
    text = (intent or "").strip()
    if not text:
        return False
    combined = "\n".join([*session_turns[-8:], thread_context or "", text])
    if not _thread_has_jira_create_context(combined):
        return False
    if _CREATE_ON_BOARD_RE.search(text):
        return True
    if _PROJECT_KEY_HINT_RE.search(text):
        return True
    if re.search(r"\b(?:yes|do it|go ahead|proceed|now|please)\b", text, re.I):
        lower = combined.lower()
        if "jira" in lower or _PROJECT_KEY_HINT_RE.search(combined) or _CREATE_ON_BOARD_RE.search(combined):
            return True
        return False
    return False
