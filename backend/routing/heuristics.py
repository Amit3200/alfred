"""Rule-based skill fallbacks when keyword triggers miss."""

from __future__ import annotations

import re

from backend.routing.git_direct import looks_like_code_investigation
from backend.routing.jira_direct import looks_like_jira_question
from backend.integrations.identity.user_identity import is_user_identity_lookup


from backend.routing.playbooks import PlaybookStore
from backend.models.config import AlfredConfig
from backend.routing.types import RouteContext, RouteDecision, RouteMode

_PLAN_COMMAND = re.compile(r"^(?:@alfred\s+)?(?:alfred\s+)?plan\b", re.IGNORECASE)
_CREATE_PR_COMMAND = re.compile(
    r"^(?:@alfred\s+)?(?:alfred\s+)?(?:pr\b|create(?:\s+a)?\s+pr\b)",
    re.IGNORECASE,
)
_CREATE_PR_HINT = re.compile(
    r"\b(?:raise|open|creat(?:e|ing)|submit|make|cut|trigger)\s+(?:a\s+|the\s+)?(?:pr|pull\s+request)\b|\bcreate_pr\b",
    re.IGNORECASE,
)
_CREATE_PR_FOLLOWUP = re.compile(
    r"\b(?:trigger|proceed|continue|go ahead|complete|finish)\b.*\b(?:pr|pull request)\b|\b(?:pr|pull request)\b.*\b(?:as per above|from above|above)\b",
    re.IGNORECASE,
)
_PENDING_PR_WORK = re.compile(
    r"\b(?:draft pr|create_pull_request|git_prepare_branch|open a draft pr|commit the changes|push the branch|opening pull request)\b",
    re.IGNORECASE,
)


def looks_like_create_pr_request(
    intent: str,
    *,
    thread_context: str | None = None,
    session_turns: tuple[str, ...] = (),
) -> bool:
    """True when the user wants Alfred to open/write a PR (not list or review one)."""
    text = intent.strip()
    if not text:
        return False
    if _CREATE_PR_COMMAND.search(text) or _CREATE_PR_HINT.search(text):
        return True
    if _CREATE_PR_FOLLOWUP.search(text):
        return True
    lower = text.lower()
    if "create_pr" in lower:
        return True

    prior = "\n".join(session_turns[-8:])
    combined = f"{prior}\n{thread_context or ''}"
    if _PENDING_PR_WORK.search(combined) and re.search(
        r"\b(?:trigger|proceed|continue|go ahead|yes|do it|commit|push|open|above|as per)\b",
        text,
        re.IGNORECASE,
    ):
        return True
    return False


def create_pr_route_decision(
    context: RouteContext,
    store: PlaybookStore,
    config: AlfredConfig,
) -> RouteDecision:
    """Route to create_pr when the user asks to open/write a PR and writes are enabled."""
    if context.mode != RouteMode.INVESTIGATION:
        return RouteDecision(
            skill_name=None,
            strategy="heuristic",
            confidence=0.0,
            reason="create_pr routing only applies to investigation",
        )
    if not config.git.enabled or not config.git.write_enabled:
        return RouteDecision(
            skill_name=None,
            strategy="heuristic",
            confidence=0.0,
            reason="git write disabled",
        )
    if not store.get_by_name("create_pr"):
        return RouteDecision(
            skill_name=None,
            strategy="heuristic",
            confidence=0.0,
            reason="create_pr skill missing",
        )
    if not looks_like_create_pr_request(
        context.intent,
        thread_context=context.thread_context,
        session_turns=context.session_turns,
    ):
        return RouteDecision(
            skill_name=None,
            strategy="heuristic",
            confidence=0.0,
            reason="not a create-pr request",
        )
    return RouteDecision(
        skill_name="create_pr",
        strategy="heuristic",
        confidence=0.97,
        reason="create PR request",
    )


def route_by_heuristic(
    context: RouteContext,
    store: PlaybookStore,
    config: AlfredConfig,
) -> RouteDecision:
    """Apply integration-specific heuristics (investigation mode only)."""
    if context.mode != RouteMode.INVESTIGATION:
        return RouteDecision(
            skill_name=None,
            strategy="heuristic",
            confidence=0.0,
            reason="heuristics only apply to investigation routing",
        )

    intent = context.intent.strip()
    if _PLAN_COMMAND.search(intent) and store.get_by_name("plan_task"):
        return RouteDecision(
            skill_name="plan_task",
            strategy="heuristic",
            confidence=0.95,
            reason="plan command heuristic",
        )

    if store.get_by_name("create_pr") and looks_like_create_pr_request(
        intent,
        thread_context=context.thread_context,
        session_turns=context.session_turns,
    ):
        return RouteDecision(
            skill_name="create_pr",
            strategy="heuristic",
            confidence=0.95,
            reason="alfred pr command heuristic",
        )

    if config.git.enabled:
        pass

        if looks_like_code_investigation(context.intent):
            if store.get_by_name("investigate_bug"):
                return RouteDecision(
                    skill_name="investigate_bug",
                    strategy="heuristic",
                    confidence=0.85,
                    reason="code investigation heuristic",
                )

    if config.jira.enabled:
        pass

        if looks_like_jira_question(context.intent):
            for name in ("jira_management", "jira_ticket"):
                if store.get_by_name(name):
                    return RouteDecision(
                        skill_name=name,
                        strategy="heuristic",
                        confidence=0.85,
                        reason="JIRA question heuristic",
                    )

    if config.slack.enabled:
        pass

        if is_user_identity_lookup(context.intent) and store.get_by_name("jira_management"):
            return RouteDecision(
                skill_name="jira_management",
                strategy="heuristic",
                confidence=0.8,
                reason="user identity lookup heuristic",
            )

    return RouteDecision(
        skill_name=None,
        strategy="heuristic",
        confidence=0.0,
        reason="no heuristic match",
    )
