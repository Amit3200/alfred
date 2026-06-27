"""Rule-based skill fallbacks when keyword triggers miss."""

from __future__ import annotations

from backend.ingress.playbooks import PlaybookStore
from backend.models.config import AlfredConfig
from backend.routing.types import RouteContext, RouteDecision, RouteMode


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

    if config.git.enabled:
        from backend.ingress.git_direct import looks_like_code_investigation

        if looks_like_code_investigation(context.intent):
            if store.get_by_name("investigate_bug"):
                return RouteDecision(
                    skill_name="investigate_bug",
                    strategy="heuristic",
                    confidence=0.85,
                    reason="code investigation heuristic",
                )

    if config.jira.enabled:
        from backend.ingress.jira_direct import looks_like_jira_question

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
        from backend.ingress.user_identity import is_user_identity_lookup

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
