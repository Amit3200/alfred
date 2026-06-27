"""LLM-based skill routing via the skill_matching provider."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from backend.ai.base import LLMProvider, Message
from backend.ingress.playbooks import PlaybookStore
from backend.routing.catalog import format_catalog_for_router, list_catalog_entries
from backend.routing.types import RouteContext, RouteDecision, RouteMode, SkillCatalogEntry

logger = logging.getLogger(__name__)

MIN_ROUTER_CONFIDENCE = 0.55
_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.I)

ROUTER_SYSTEM_PROMPT = """You are Alfred's skill router. Given the user message and skill catalog, choose at most one skill that should handle the request.

Respond with JSON only (no markdown prose):
{"skill": "<exact_skill_name_or_null>", "confidence": 0.0, "reason": "<brief>"}

Rules:
- Use exact skill names from the catalog, or null when no skill fits.
- Prefer investigation skills for code, JIRA, AWS, Google Workspace, PR, or data tasks.
- Use thread/session context when the user refers to "this", "that", or prior messages.
- Return null for pure chitchat, greetings, or questions outside registered skills.
- confidence is 0.0–1.0; only pick a skill when confidence >= 0.55."""


class LLMSkillMatcher:
    """Agentic skill selection using a cheap/fast LLM call."""

    def __init__(
        self,
        provider: LLMProvider,
        *,
        model: str = "",
        min_confidence: float = MIN_ROUTER_CONFIDENCE,
    ) -> None:
        self._provider = provider
        self._model = model
        self._min_confidence = min_confidence

    def match(
        self,
        context: RouteContext,
        store: PlaybookStore,
    ) -> RouteDecision:
        entries = list_catalog_entries(
            store,
            mode=context.mode,
            channel_id=context.channel_id,
            repo=context.repo,
        )
        if not entries:
            return RouteDecision(
                skill_name=None,
                strategy="llm",
                confidence=0.0,
                reason="empty skill catalog",
            )

        user_prompt = _build_user_prompt(context, entries)
        try:
            from backend.observability.context import set_call_kind

            set_call_kind("skill_matching")
            response = self._provider.chat(
                [
                    Message(role="system", content=ROUTER_SYSTEM_PROMPT),
                    Message(role="user", content=user_prompt),
                ],
                model=self._model or None,
            )
        except Exception as exc:
            logger.warning("LLM skill router failed: %s", exc)
            return RouteDecision(
                skill_name=None,
                strategy="llm",
                confidence=0.0,
                reason=f"router error: {exc}",
            )

        parsed = parse_router_json(response.content or "")
        if not parsed:
            logger.info("LLM skill router returned unparseable response")
            return RouteDecision(
                skill_name=None,
                strategy="llm",
                confidence=0.0,
                reason="unparseable router response",
            )

        skill_name = _normalize_skill_name(parsed.get("skill"))
        confidence = _normalize_confidence(parsed.get("confidence"))
        reason = str(parsed.get("reason") or "").strip() or "llm router"

        if not skill_name:
            return RouteDecision(
                skill_name=None,
                strategy="llm",
                confidence=confidence,
                reason=reason or "llm chose no skill",
            )

        if confidence < self._min_confidence:
            return RouteDecision(
                skill_name=None,
                strategy="llm",
                confidence=confidence,
                reason=f"below confidence threshold ({confidence:.2f}): {reason}",
            )

        if not _skill_valid(skill_name, entries):
            return RouteDecision(
                skill_name=None,
                strategy="llm",
                confidence=confidence,
                reason=f"unknown or ineligible skill {skill_name!r}",
            )

        logger.info(
            "LLM skill router matched %s (confidence=%.2f): %s",
            skill_name,
            confidence,
            reason,
        )
        return RouteDecision(
            skill_name=skill_name,
            strategy="llm",
            confidence=confidence,
            reason=reason,
        )


def parse_router_json(text: str) -> dict[str, Any] | None:
    """Extract a JSON object from model output."""
    raw = (text or "").strip()
    if not raw:
        return None

    for candidate in (raw, *_json_candidates(raw)):
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    return None


def _json_candidates(text: str) -> list[str]:
    candidates: list[str] = []
    if match := _JSON_BLOCK_RE.search(text):
        candidates.append(match.group(1).strip())
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        candidates.append(text[start : end + 1])
    return candidates


def _build_user_prompt(context: RouteContext, entries: list[SkillCatalogEntry]) -> str:
    parts = [
        format_catalog_for_router(entries, mode=context.mode),
        "",
        f"User message:\n{context.intent.strip()}",
    ]
    if context.thread_context:
        snippet = context.thread_context.strip()
        if len(snippet) > 3000:
            snippet = snippet[:3000] + "\n… (truncated)"
        parts.extend(["", "Thread context:", snippet])
    if context.session_turns:
        parts.extend(["", "Recent session turns:"])
        parts.extend(f"- {turn}" for turn in context.session_turns[-4:])
    return "\n".join(parts)


def _normalize_skill_name(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"null", "none", "nil"}:
        return None
    return text


def _normalize_confidence(value: Any) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, score))


def _skill_valid(skill_name: str, entries: list[SkillCatalogEntry]) -> bool:
    names = {entry.name.lower() for entry in entries}
    return skill_name.lower() in names
