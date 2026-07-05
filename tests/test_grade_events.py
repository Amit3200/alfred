"""Tests for grade_events SQL guardrails."""

from __future__ import annotations

from datetime import UTC, datetime

from backend.integrations.aws.grade_events import GradeEventsFilters, build_grade_events_sql
from backend.models.config import AWSConfig, AlfredConfig


def _config() -> AlfredConfig:
    config = AlfredConfig()
    config.aws = AWSConfig(
        enabled=True,
        athena_database="analytics",
        grade_events_table="grade_events",
    )
    return config


def test_no_filters_uses_two_hour_window_and_limit_200():
    fixed = datetime(2026, 6, 21, 15, 30, tzinfo=UTC)
    sql, guardrails = build_grade_events_sql(
        _config(),
        GradeEventsFilters(),
        now=fixed,
    )
    assert "LIMIT 200" in sql
    assert guardrails["time_window"] == "last_2_hours"
    assert "date = '2026-06-21'" in sql
    assert "hour = '14'" in sql or "hour = '15'" in sql


def test_entity_filters_without_date_use_one_day_window():
    fixed = datetime(2026, 6, 21, 15, 30, tzinfo=UTC)
    sql, guardrails = build_grade_events_sql(
        _config(),
        GradeEventsFilters(session_id="sess-123"),
        now=fixed,
    )
    assert "LIMIT 200" in sql
    assert guardrails["time_window"] == "last_1_day"
    assert "session_id = 'sess-123'" in sql
    assert "date = '2026-06-21'" in sql or "date >=" in sql


def test_explicit_date_skips_default_window():
    sql, guardrails = build_grade_events_sql(
        _config(),
        GradeEventsFilters(date="2026-06-20", merchant_id="m1"),
    )
    assert "date = '2026-06-20'" in sql
    assert "time_window" not in guardrails
    assert "merchant_id = 'm1'" in sql


def test_full_data_allows_higher_limit():
    sql, guardrails = build_grade_events_sql(
        _config(),
        GradeEventsFilters(kind="checkout_started"),
        full_data=True,
        limit=1000,
    )
    assert "LIMIT 1000" in sql
    assert guardrails["full_data"] is True
