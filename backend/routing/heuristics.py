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

    if _CREATE_PR_COMMAND.search(intent) and store.get_by_name("create_pr"):
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
