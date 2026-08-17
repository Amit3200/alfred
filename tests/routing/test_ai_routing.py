"""Tests for per-task LLM routing (provider + model)."""

from __future__ import annotations

from unittest.mock import MagicMock

from backend.ai.routing import effective_route, resolve_llm_route
from backend.models.config import AIConfig, AIProviderConfig, LLMRouteConfig


def _ai_config(**overrides) -> AIConfig:
    base = dict(
        default_provider="kimi",
        routing={
            "skill_matching": {"provider": "ollama", "model": "llama3.2:3b"},
            "investigation": {"provider": "kimi", "model": "kimi-k2.6"},
            "workflow_execution": {"provider": "anthropic", "model": ""},
            "basic_chat": {"provider": "", "model": ""},
            "pr_review": {"provider": "", "model": ""},
        },
        providers={
            "ollama": AIProviderConfig(
                enabled=True,
                base_url="http://localhost:11434/v1",
                model="llama3",
            ),
            "kimi": AIProviderConfig(
                enabled=True,
                api_key="sk-test",
                model="kimi-k2.6",
            ),
            "anthropic": AIProviderConfig(
                enabled=False,
                model="claude-sonnet-4-20250514",
            ),
        },
    )
    base.update(overrides)
    return AIConfig(**base)


def test_legacy_string_routing_coerced():
    ai = AIConfig(
        default_provider="kimi",
        routing={"investigation": "kimi"},
        providers={"kimi": AIProviderConfig(enabled=True, model="kimi-k2.6")},
    )
    assert ai.routing.investigation == LLMRouteConfig(provider="kimi", model="")


def test_effective_route_uses_investigation_for_pr_review_fallback():
    ai = _ai_config()
    route = effective_route(ai, "pr_review")
    assert route.provider == "kimi"
    assert route.model == "kimi-k2.6"


def test_effective_route_basic_chat_uses_default_provider():
    ai = _ai_config()
    route = effective_route(ai, "basic_chat")
    assert route.provider == "kimi"
    assert route.model == ""


def test_effective_route_model_override_without_provider():
    ai = _ai_config(
        routing={
            "investigation": {"provider": "kimi", "model": "kimi-k2.6"},
            "pr_review": {"provider": "", "model": "kimi-k2.5"},
        },
    )
    route = effective_route(ai, "pr_review")
    assert route.provider == "kimi"
    assert route.model == "kimi-k2.5"


def test_resolve_llm_route_returns_provider_and_model():
    ai = _ai_config()
    router = MagicMock()
    mock_provider = MagicMock()
    mock_provider.is_available.return_value = True
    router.get.return_value = mock_provider

    name, provider, model = resolve_llm_route(ai, "investigation", router=router)

    assert name == "kimi"
    assert provider is mock_provider
    assert model == "kimi-k2.6"
    router.get.assert_called_with("kimi")


def test_resolve_llm_route_falls_back_when_routed_provider_unavailable():
    ai = _ai_config(
        routing={"investigation": {"provider": "anthropic", "model": "claude-opus-4-20250514"}},
    )
    router = MagicMock()
    unavailable = MagicMock()
    unavailable.is_available.return_value = False
    fallback_provider = MagicMock()
    fallback_provider.is_available.return_value = True

    def get_side_effect(name: str):
        if name == "anthropic":
            return unavailable
        return fallback_provider

    router.get.side_effect = get_side_effect

    name, _, model = resolve_llm_route(ai, "investigation", router=router)

    assert name == "kimi"
    assert model == "kimi-k2.6"
