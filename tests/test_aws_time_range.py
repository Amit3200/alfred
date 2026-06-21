"""Tests for AWS time range parsing."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from backend.aws.time_range import parse_time, resolve_time_range


def test_parse_relative_hours():
    before = datetime.now(UTC)
    parsed = parse_time("2h")
    assert parsed is not None
    assert before - parsed >= timedelta(hours=1, minutes=59)


def test_resolve_time_range_defaults():
    start, end = resolve_time_range(None, None, default_hours=1)
    assert start < end
    assert end - start <= timedelta(hours=1, seconds=5)
