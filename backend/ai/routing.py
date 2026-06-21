"""Resolve provider + model for per-task LLM routing."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from backend.models.config import AIConfig, LLMRouteConfig

if TYPE_CHECKING:
    from backend.ai.registry import LLMRouter

TASK_TYPES = (
    "skill_matching",
    "investigation",
    "workflow_execution",
    "basic_chat",
    "pr_review",
)


def effective_route(ai: AIConfig, task_type: str) -> LLMRouteConfig:
    """Return the routing entry for *task_type*, applying fallback rules."""
    route = getattr(ai.routing, task_type, None) or LLMRouteConfig()
    if route.provider:
        return route

    model_override = route.model
    if task_type == "pr_review":
        inv = ai.routing.investigation
        if inv.provider:
            return LLMRouteConfig(
                provider=inv.provider,
                model=model_override or inv.model,
            )
    if task_type == "basic_chat":
        return LLMRouteConfig(provider=ai.default_provider, model=model_override)

    inv = ai.routing.investigation
    if task_type != "investigation" and inv.provider:
        return LLMRouteConfig(provider=inv.provider, model=model_override or inv.model)

    return LLMRouteConfig(provider=ai.default_provider, model=model_override)


def resolve_llm_route(
    ai: AIConfig,
    task_type: str,
    *,
    router: LLMRouter,
) -> tuple[str, Any, str]:
    """Return ``(provider_name, provider, model_name)`` for a task kind."""
    route = effective_route(ai, task_type)
    provider_name = route.provider or ai.default_provider
    model = route.model

    cfg = ai.providers.get(provider_name)
    if cfg and cfg.enabled:
        try:
            provider = router.get(provider_name)
            if provider.is_available():
                return provider_name, provider, model or cfg.model or ""
        except KeyError:
            pass

    provider_name = ai.default_provider
    provider = router.get(provider_name)
    cfg = ai.providers[provider_name]
    return provider_name, provider, cfg.model or ""
