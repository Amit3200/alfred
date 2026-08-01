"""Direct JIRA tool routing for unambiguous ticket questions."""

from __future__ import annotations
from backend.integrations.identity.user_identity import (
    detect_user_identity_action,
    looks_like_jira_create_request,
)


import re
from typing import Any

from backend.routing.jira_context import detect_jira_list_action
from backend.integrations.jira.api import extract_issue_key
from backend.models.config import AlfredConfig
from backend.models.task import Task

_JIRA_URL_RE = re.compile(
    r"atlassian\.net/browse/([A-Z][A-Z0-9]+-\d+)",
    re.I,
)

_STATUS_HINTS = (
    "status of",
    "state of",
    "what is",
    "what's",
    "show",
    "get",
    "details for",
    "tell me about",
)


def extract_jira_issue_key(text: str) -> str | None:
    if match := _JIRA_URL_RE.search(text or ""):
        return match.group(1).upper()
    return extract_issue_key(text)


def looks_like_jira_question(intent: str) -> bool:
    lower = intent.lower()
    if extract_jira_issue_key(intent):
        return True
    if "jira" in lower and any(h in lower for h in ("ticket", "issue", "status", "open")):
        return True
    return False


def detect_jira_direct_action(
    intent: str,
    config: AlfredConfig,
    task: Task | None = None,
    *,
    data_dir: Any | None = None,
    session: Any | None = None,
) -> tuple[str, dict[str, Any]] | None:
    if task is not None:
        if looks_like_jira_create_request(intent):
            return None

        if identity := detect_user_identity_action(
            intent, config, task, session=session, data_dir=data_dir
        ):
            return identity

    if not config.jira.enabled:
        return None

    if task is not None:
        if listed := detect_jira_list_action(intent, config, task, data_dir=data_dir):
            return listed

    key = extract_jira_issue_key(intent)
    if not key and session:
        key = (session.metadata or {}).get("active_jira_ticket")
    if not key:
        return None
    lower = intent.lower()
    if any(h in lower for h in _STATUS_HINTS) or "jira" in lower or _JIRA_URL_RE.search(intent) or (session and (session.metadata or {}).get("active_jira_ticket") == key):
        return "get_jira_issue", {"issue_key": key}
    return None
