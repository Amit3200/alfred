"""Tests for AI observability storage and recording."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.observability.models import InteractionEvent, ObservabilityFilters
from backend.observability.recorder import ObservabilityRecorder
from backend.observability.store import SQLiteObservabilityStore


def _event(**kwargs) -> InteractionEvent:
    defaults = {
        "recorded_at": datetime.now(timezone.utc),
        "event_type": "llm_call",
        "source": "slack",
        "user_id": "U123",
        "user_label": "amit",
        "provider": "kimi",
        "model": "kimi-k2.6",
        "call_kind": "investigation",
        "prompt_tokens": 100,
        "completion_tokens": 50,
        "total_tokens": 150,
    }
    defaults.update(kwargs)
    return InteractionEvent(**defaults)


def test_store_records_and_summarizes(tmp_path):
    store = SQLiteObservabilityStore(tmp_path)
    recorder = ObservabilityRecorder(store)

    recorder.store.record(
        _event(event_type="tool_call", tool_name="grep_repo", tool_category="git", total_tokens=0)
    )
    recorder.store.record(_event(total_tokens=150))
    recorder.store.record(
        _event(
            source="ui",
            user_label="admin-ui",
            model="llama3",
            provider="ollama",
            total_tokens=20,
        )
    )

    summary = store.summary(ObservabilityFilters())
    assert summary.llm_calls == 2
    assert summary.tool_calls == 1
    assert summary.total_tokens == 170
    assert summary.by_user["amit"] == 2
    assert summary.by_user["admin-ui"] == 1
    assert summary.by_source["slack"] == 2
    assert summary.by_tool_category["git"] == 1


def test_timeseries_buckets_by_day(tmp_path):
    store = SQLiteObservabilityStore(tmp_path)
    now = datetime.now(timezone.utc)
    store.record(_event(recorded_at=now, total_tokens=10))
    store.record(_event(recorded_at=now - timedelta(days=1), total_tokens=5))

    series = store.timeseries(ObservabilityFilters(), bucket="day")
    assert len(series.points) == 2
    assert sum(point.llm_calls for point in series.points) == 2
    assert sum(point.total_tokens for point in series.points) == 15


def test_list_events_respects_filters(tmp_path):
    store = SQLiteObservabilityStore(tmp_path)
    store.record(_event(source="slack", user_label="amit"))
    store.record(_event(source="ui", user_label="admin-ui"))

    page = store.list_events(
        ObservabilityFilters(source="slack", user_label="amit"),
        limit=10,
    )
    assert page.total == 1
    assert page.events[0].source == "slack"


def test_parse_token_usage_openai_shape():
    from backend.observability.usage import parse_token_usage

    prompt, completion, total = parse_token_usage(
        "openai",
        {"usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18}},
    )
    assert (prompt, completion, total) == (11, 7, 18)
