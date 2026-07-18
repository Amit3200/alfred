"""BM25 skill matching — fuzzy routing between keyword/heuristic and LLM tiers."""

from __future__ import annotations

import re

from backend.models.config import AlfredConfig
from backend.routing.catalog import list_catalog_entries
from backend.routing.playbooks import PlaybookStore
from backend.routing.types import RouteContext, RouteDecision, SkillCatalogEntry

_TOKEN_RE = re.compile(r"[a-z0-9_]{2,}")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall((text or "").lower())


def _entry_document(entry: SkillCatalogEntry) -> list[str]:
    parts = [entry.name.replace("_", " "), entry.description]
    parts.extend(entry.triggers)
    parts.extend(entry.repos)
    return _tokenize(" ".join(part for part in parts if part))


def _build_query(context: RouteContext) -> list[str]:
    parts = [context.intent]
    if context.thread_context:
        parts.append(context.thread_context[:1500])
    parts.extend(context.session_turns[-2:])
    return _tokenize(" ".join(parts))


def _normalize_confidence(score: float, *, min_score: float) -> float:
    if min_score <= 0:
        return min(max(score / 10.0, 0.0), 0.95)
    return min(max(score / (min_score * 2.0), 0.0), 0.95)


def route_by_bm25(
    context: RouteContext,
    store: PlaybookStore,
    config: AlfredConfig,
) -> RouteDecision:
    """Pick the best skill via BM25 over catalog metadata when keyword/heuristic miss."""
    skills = config.skills
    if not getattr(skills, "bm25_routing", True):
        return RouteDecision(
            skill_name=None,
            strategy="bm25",
            confidence=0.0,
            reason="bm25 routing disabled",
        )

    entries = list_catalog_entries(
        store,
        mode=context.mode,
        channel_id=context.channel_id,
        repo=context.repo,
    )
    if not entries:
        return RouteDecision(
            skill_name=None,
            strategy="bm25",
            confidence=0.0,
            reason="no routable skills for BM25",
        )

    query = _build_query(context)
    if not query:
        return RouteDecision(
            skill_name=None,
            strategy="bm25",
            confidence=0.0,
            reason="empty query tokens",
        )

    try:
        from rank_bm25 import BM25Okapi
    except ImportError:
        return RouteDecision(
            skill_name=None,
            strategy="bm25",
            confidence=0.0,
            reason="rank-bm25 not installed",
        )

    corpus = [_entry_document(entry) for entry in entries]
    if not any(corpus):
        return RouteDecision(
            skill_name=None,
            strategy="bm25",
            confidence=0.0,
            reason="empty BM25 corpus",
        )

    model = BM25Okapi(corpus)
    scores = list(model.get_scores(query))
    ranked = sorted(
        zip(scores, entries, strict=False),
        key=lambda item: item[0],
        reverse=True,
    )
    top_score, top_entry = ranked[0]
    second_score = ranked[1][0] if len(ranked) > 1 else 0.0

    min_score = float(getattr(skills, "bm25_min_score", 2.0))
    min_gap = float(getattr(skills, "bm25_min_gap", 0.5))

    if top_score < min_score:
        return RouteDecision(
            skill_name=None,
            strategy="bm25",
            confidence=_normalize_confidence(top_score, min_score=min_score),
            reason=f"top BM25 score {top_score:.2f} below min {min_score:.2f}",
        )
    if len(ranked) > 1 and (top_score - second_score) < min_gap:
        return RouteDecision(
            skill_name=None,
            strategy="bm25",
            confidence=_normalize_confidence(top_score, min_score=min_score),
            reason=f"ambiguous BM25 match (gap {top_score - second_score:.2f} < {min_gap:.2f})",
        )

    return RouteDecision(
        skill_name=top_entry.name,
        strategy="bm25",
        confidence=_normalize_confidence(top_score, min_score=min_score),
        reason=f"BM25 matched {top_entry.name} (score={top_score:.2f})",
    )
