"""Approximate LLM cost estimation from token usage and model rates."""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.models.config import ModelPricingConfig, ObservabilityConfig

# USD per 1M tokens — approximate defaults; override in config.yaml.
_DEFAULT_MODEL_RATES: dict[str, tuple[float, float]] = {
    # Moonshot Kimi
    "kimi-k2.6": (0.60, 2.40),
    "kimi-k2": (0.60, 2.40),
    "moonshot-v1-8k": (0.20, 0.20),
    "moonshot-v1-32k": (0.40, 0.40),
    "moonshot-v1-128k": (0.60, 0.60),
    # Anthropic
    "claude-sonnet-4-20250514": (3.00, 15.00),
    "claude-3-5-sonnet-20241022": (3.00, 15.00),
    "claude-3-5-haiku-20241022": (0.80, 4.00),
    "claude-3-opus-20240229": (15.00, 75.00),
    # OpenAI
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
    # Google
    "gemini-2.0-flash": (0.10, 0.40),
    "gemini-2.5-flash": (0.15, 0.60),
    "gemini-2.5-pro": (1.25, 10.00),
    # Local
    "llama3": (0.0, 0.0),
    "llama3.1": (0.0, 0.0),
    "llama3.2": (0.0, 0.0),
}

_DEFAULT_PROVIDER_RATES: dict[str, tuple[float, float]] = {
    "ollama": (0.0, 0.0),
    "kimi": (0.60, 2.40),
    "anthropic": (3.00, 15.00),
    "openai": (0.15, 0.60),
    "gemini": (0.10, 0.40),
}


@dataclass
class PricingTable:
    """Resolved per-model and per-provider token rates (USD / 1M tokens)."""

    model_rates: dict[str, tuple[float, float]] = field(default_factory=dict)
    provider_rates: dict[str, tuple[float, float]] = field(default_factory=dict)

    def estimate(
        self,
        *,
        provider: str | None,
        model: str | None,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> float:
        input_rate, output_rate = self._resolve_rates(provider, model)
        cost = (prompt_tokens / 1_000_000) * input_rate + (completion_tokens / 1_000_000) * output_rate
        return round(cost, 6)

    def _resolve_rates(
        self,
        provider: str | None,
        model: str | None,
    ) -> tuple[float, float]:
        model_key = _normalize_key(model)
        if model_key:
            if model_key in self.model_rates:
                return self.model_rates[model_key]
            for key, rates in self.model_rates.items():
                if model_key.startswith(key) or key.startswith(model_key):
                    return rates

        provider_key = _normalize_key(provider)
        if provider_key and provider_key in self.provider_rates:
            return self.provider_rates[provider_key]

        return (0.0, 0.0)


def build_pricing_table(config: ObservabilityConfig | None = None) -> PricingTable:
    """Merge built-in defaults with observability.model_pricing overrides."""
    model_rates = dict(_DEFAULT_MODEL_RATES)
    provider_rates = dict(_DEFAULT_PROVIDER_RATES)

    if config is not None:
        for name, entry in (config.model_pricing or {}).items():
            key = _normalize_key(name)
            if key:
                model_rates[key] = (entry.input_per_million, entry.output_per_million)
        for name, entry in (config.provider_pricing or {}).items():
            key = _normalize_key(name)
            if key:
                provider_rates[key] = (entry.input_per_million, entry.output_per_million)

    return PricingTable(model_rates=model_rates, provider_rates=provider_rates)


def estimate_event_cost(
    *,
    provider: str | None,
    model: str | None,
    prompt_tokens: int,
    completion_tokens: int,
    pricing: PricingTable | None = None,
) -> float:
    table = pricing or build_pricing_table()
    return table.estimate(
        provider=provider,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )


def _normalize_key(value: str | None) -> str:
    return (value or "").strip().lower()
