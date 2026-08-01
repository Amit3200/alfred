"""Direct JIRA tool routing for unambiguous ticket questions."""

from __future__ import annotations

import re
from typing import Any

from backend.routing.jira_context import detect_jira_list_action
from backend.routing.jira_intent import looks_like_jira_create_followup, looks_like_jira_create_request
from backend.integrations.jira.api import extract_issue_key
from backend.models.config import AlfredConfig
from backend.models.task import Task
from backend.routing.playbooks import PlaybookStore
from backend.routing.types import RouteContext, RouteDecision, RouteMode

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


def looks_like_jira_question(
    intent: str,
    *,
    session_turns: tuple[str, ...] = (),
    thread_context: str | None = None,
) -> bool:
    if looks_like_jira_create_request(intent):
        return True
    if looks_like_jira_create_followup(
        intent,
        session_turns=session_turns,
        thread_context=thread_context,
    ):
        return True
    lower = intent.lower()
    if extract_jira_issue_key(intent):
        return True
    if "jira" in lower and any(h in lower for h in ("ticket", "issue", "status", "open")):
        return True
    if any(h in lower for h in ("ticket", "issue", "bug")) and any(
        h in lower for h in ("board", "project key", " ts", "ts ", "tech-support")
    ):
        return True
    return False


def jira_create_route_decision(
    context: RouteContext,
    store: PlaybookStore,
    config: AlfredConfig,
) -> RouteDecision:
    """Route to jira_management when the user wants to create issues (including thread follow-ups)."""
    if context.mode != RouteMode.INVESTIGATION:
        return RouteDecision(
            skill_name=None,
            strategy="heuristic",
            confidence=0.0,
            reason="jira create routing only applies to investigation",
        )
    if not config.jira.enabled:
        return RouteDecision(
            skill_name=None,
            strategy="heuristic",
            confidence=0.0,
            reason="jira disabled",
        )
    if not store.get_by_name("jira_management"):
        return RouteDecision(
            skill_name=None,
            strategy="heuristic",
            confidence=0.0,
            reason="jira_management skill missing",
        )
    if looks_like_jira_create_request(context.intent):
        return RouteDecision(
            skill_name="jira_management",
            strategy="heuristic",
            confidence=0.98,
            reason="JIRA create request",
        )
    if looks_like_jira_create_followup(
        context.intent,
        session_turns=context.session_turns,
        thread_context=context.thread_context,
    ):
        return RouteDecision(
            skill_name="jira_management",
            strategy="heuristic",
            confidence=0.96,
            reason="JIRA create thread follow-up",
        )
    return RouteDecision(
        skill_name=None,
        strategy="heuristic",
        confidence=0.0,
        reason="not a JIRA create request",
    )


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

        from backend.integrations.identity.user_identity import detect_user_identity_action

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
