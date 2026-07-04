"""Keyword trigger routing — substring match on skill frontmatter."""

from __future__ import annotations

from backend.routing.playbooks import Playbook, PlaybookStore
from backend.routing.types import RouteContext, RouteDecision, RouteMode


def route_by_keyword(context: RouteContext, store: PlaybookStore) -> RouteDecision:
    """Match skills whose trigger keywords appear in the user intent."""
    if context.mode == RouteMode.INVESTIGATION:
        playbook = store.pick_investigation(
            context.intent,
            channel_id=context.channel_id,
            repo=context.repo,
        )
    else:
        playbook = store.pick_conversational(
            context.intent,
            channel_id=context.channel_id,
            repo=context.repo,
        )

    if playbook is None:
        return RouteDecision(
            skill_name=None,
            strategy="keyword",
            confidence=0.0,
            reason="no trigger keyword match",
        )

    return RouteDecision(
        skill_name=playbook.name,
        strategy="keyword",
        confidence=1.0,
        reason=f"trigger keyword matched ({playbook.name})",
    )


def playbook_for_decision(decision: RouteDecision, store: PlaybookStore) -> Playbook | None:
    if not decision.skill_name:
        return None
    return store.get_by_name(decision.skill_name)
