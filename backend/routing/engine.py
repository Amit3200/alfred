"""Hybrid skill router — keyword → heuristics → BM25 → LLM."""

from __future__ import annotations

import logging

from typing import TYPE_CHECKING

from backend.ai.registry import LLMRouter
if TYPE_CHECKING:
    from backend.routing.playbooks import PlaybookStore
from backend.models.config import AlfredConfig
from backend.routing.bm25 import route_by_bm25
from backend.routing.heuristics import create_pr_route_decision, route_by_heuristic
from backend.routing.jira_direct import jira_create_route_decision
from backend.routing.keyword import playbook_for_decision, route_by_keyword
from backend.routing.llm import LLMSkillMatcher
from backend.routing.tool_availability import playbook_has_runnable_tools
from backend.routing.types import RouteContext, RouteDecision, RouteMode, RouteResult

logger = logging.getLogger(__name__)


class SkillRouter:
    """Independent routing SDK entry point for Alfred playbooks/skills."""

    def __init__(
        self,
        config: AlfredConfig,
        store: PlaybookStore,
        *,
        llm_router: LLMRouter | None = None,
    ) -> None:
        self._config = config
        self._store = store
        self._llm_router = llm_router
        self._llm_matcher: LLMSkillMatcher | None = None

    def route(self, context: RouteContext) -> RouteResult:
        """Resolve the best playbook for *context* using layered strategies."""
        if context.mode == RouteMode.INVESTIGATION:
            create_pr = create_pr_route_decision(context, self._store, self._config)
            if create_pr.matched:
                playbook = playbook_for_decision(create_pr, self._store)
                if playbook is not None and playbook_has_runnable_tools(
                    playbook.allowed_tools, self._config
                ):
                    logger.debug("Skill route: %s via create-pr priority", playbook.name)
                    return RouteResult(playbook=playbook, decision=create_pr)

            jira_create = jira_create_route_decision(context, self._store, self._config)
            if jira_create.matched:
                playbook = playbook_for_decision(jira_create, self._store)
                if playbook is not None and playbook_has_runnable_tools(
                    playbook.allowed_tools, self._config
                ):
                    logger.debug("Skill route: %s via jira-create priority", playbook.name)
                    return RouteResult(playbook=playbook, decision=jira_create)

        phrase_routing = self._phrase_routing_enabled()
        keyword = route_by_keyword(context, self._store)
        if keyword.matched:
            playbook = playbook_for_decision(keyword, self._store)
            if playbook is not None:
                skip_investigation_phrase = (
                    context.mode == RouteMode.INVESTIGATION
                    and not phrase_routing
                    and playbook.mode in ("investigation", "workflow")
                )
                if not skip_investigation_phrase:
                    if playbook_has_runnable_tools(playbook.allowed_tools, self._config):
                        logger.debug("Skill route: %s via keyword", playbook.name)
                        return RouteResult(playbook=playbook, decision=keyword)
                    logger.warning(
                        "Skipping keyword match for %s — no runnable tools in %s",
                        playbook.name,
                        playbook.allowed_tools,
                    )

        if context.mode == RouteMode.INVESTIGATION and phrase_routing:
            heuristic = route_by_heuristic(context, self._store, self._config)
            if heuristic.matched:
                playbook = playbook_for_decision(heuristic, self._store)
                if playbook is not None and playbook_has_runnable_tools(
                    playbook.allowed_tools, self._config
                ):
                    logger.debug("Skill route: %s via heuristic", playbook.name)
                    return RouteResult(playbook=playbook, decision=heuristic)

        if phrase_routing and self._bm25_enabled():
            bm25 = route_by_bm25(context, self._store, self._config)
            if bm25.matched:
                playbook = playbook_for_decision(bm25, self._store)
                if playbook is not None and playbook_has_runnable_tools(
                    playbook.allowed_tools, self._config
                ):
                    logger.debug("Skill route: %s via BM25", playbook.name)
                    return RouteResult(playbook=playbook, decision=bm25)

        if self._agentic_enabled():
            llm = self._route_by_llm(context)
            if llm.matched:
                playbook = playbook_for_decision(llm, self._store)
                if playbook is not None and playbook_has_runnable_tools(
                    playbook.allowed_tools, self._config
                ):
                    return RouteResult(playbook=playbook, decision=llm)

        return RouteResult.none(reason="no keyword, heuristic, BM25, or LLM match")

    def route_investigation(self, context: RouteContext) -> RouteResult:
        """Convenience wrapper for investigation/workflow skills."""
        return self.route(
            RouteContext(
                intent=context.intent,
                channel_id=context.channel_id,
                repo=context.repo,
                mode=RouteMode.INVESTIGATION,
                thread_context=context.thread_context,
                session_turns=context.session_turns,
            )
        )

    def route_conversational(self, context: RouteContext) -> RouteResult:
        """Convenience wrapper for conversational playbooks."""
        return self.route(
            RouteContext(
                intent=context.intent,
                channel_id=context.channel_id,
                repo=context.repo,
                mode=RouteMode.CONVERSATIONAL,
                thread_context=context.thread_context,
                session_turns=context.session_turns,
            )
        )

    def _agentic_enabled(self) -> bool:
        return bool(getattr(self._config.skills, "agentic_routing", True))

    def _bm25_enabled(self) -> bool:
        return bool(getattr(self._config.skills, "bm25_routing", True))

    def _phrase_routing_enabled(self) -> bool:
        return bool(getattr(self._config.routing, "phrase_routing_enabled", False))

    def _route_by_llm(self, context: RouteContext) -> RouteDecision:
        matcher = self._get_llm_matcher()
        if matcher is None:
            return RouteDecision(
                skill_name=None,
                strategy="llm",
                confidence=0.0,
                reason="skill_matching provider unavailable",
            )
        return matcher.match(context, self._store)

    def _get_llm_matcher(self) -> LLMSkillMatcher | None:
        if self._llm_matcher is not None:
            return self._llm_matcher

        if self._llm_router is None:
            return None

        try:
            provider_name, provider, model = self._llm_router.resolve_task("skill_matching")
            if not provider.is_available():
                logger.debug("skill_matching provider %s unavailable", provider_name)
                return None
            matcher = LLMSkillMatcher(provider, model=model)
            self._llm_matcher = matcher
            return matcher
        except Exception as exc:
            logger.debug("Could not build LLM skill matcher: %s", exc)
            return None
