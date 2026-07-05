"""Tests for approximate LLM cost estimation."""

from __future__ import annotations
from backend.observability.models import InteractionEvent, ObservabilityFilters
from backend.observability.store import SQLiteObservabilityStore


from backend.models.config import ModelPricingConfig, ObservabilityConfig
from backend.observability.pricing import build_pricing_table, estimate_event_cost


def test_estimate_kimi_k26_default_rates():
    cost = estimate_event_cost(
        provider="kimi",
        model="kimi-k2.6",
        prompt_tokens=1_000_000,
        completion_tokens=500_000,
    )
    # 1M input @ $0.60 + 0.5M output @ $2.40 = $0.60 + $1.20 = $1.80
    assert cost == 1.8


def test_ollama_is_free_by_default():
    cost = estimate_event_cost(
        provider="ollama",
        model="llama3",
        prompt_tokens=50_000,
        completion_tokens=10_000,
    )
    assert cost == 0.0


def test_config_override_model_pricing():
    table = build_pricing_table(
        ObservabilityConfig(
            model_pricing={
                "kimi-k2.6": ModelPricingConfig(input_per_million=1.0, output_per_million=4.0),
            }
        )
    )
    cost = table.estimate(
        provider="kimi",
        model="kimi-k2.6",
        prompt_tokens=1_000_000,
        completion_tokens=0,
    )
    assert cost == 1.0


def test_store_summary_includes_cost(tmp_path):
    pass
    pass

    store = SQLiteObservabilityStore(tmp_path)
    store.record(
        InteractionEvent(
            recorded_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
            event_type="llm_call",
            source="slack",
            provider="kimi",
            model="kimi-k2.6",
            prompt_tokens=1000,
            completion_tokens=500,
            total_tokens=1500,
        )
    )
    summary = store.summary(ObservabilityFilters())
    assert summary.estimated_cost_usd > 0
