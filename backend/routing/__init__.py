"""Alfred routing SDK — plan-first tool planning, policy skills, and SkillRouter fallback."""

from __future__ import annotations

from typing import Any

from backend.routing.types import RouteContext, RouteDecision, RouteMode, RouteResult, SkillCatalogEntry

__all__ = [
    "LLMSkillMatcher",
    "RouteContext",
    "RouteDecision",
    "RouteMode",
    "RouteResult",
    "SkillCatalogEntry",
    "SkillRouter",
    "parse_router_json",
]


def __getattr__(name: str) -> Any:
    if name == "SkillRouter":
        from backend.routing.engine import SkillRouter

        return SkillRouter
    if name == "LLMSkillMatcher":
        from backend.routing.llm import LLMSkillMatcher

        return LLMSkillMatcher
    if name == "parse_router_json":
        from backend.routing.llm import parse_router_json

        return parse_router_json
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
