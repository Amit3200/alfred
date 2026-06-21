"""Parse relative and ISO time ranges for CloudWatch Logs."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

_RELATIVE = re.compile(r"^(\d+)(m|h|d)$", re.IGNORECASE)


def parse_time(value: str | None, *, default: datetime | None = None) -> datetime | None:
    if value is None or not str(value).strip():
        return default
    text = str(value).strip()
    match = _RELATIVE.match(text)
    if match:
        amount = int(match.group(1))
        unit = match.group(2).lower()
        if unit == "m":
            delta = timedelta(minutes=amount)
        elif unit == "h":
            delta = timedelta(hours=amount)
        else:
            delta = timedelta(days=amount)
        return datetime.now(UTC) - delta
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(
            f"Invalid time '{text}'. Use ISO8601 (2024-01-15T12:00:00Z) or relative (30m, 1h, 7d)."
        ) from exc
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def resolve_time_range(
    start_time: str | None,
    end_time: str | None,
    *,
    default_hours: int = 1,
) -> tuple[datetime, datetime]:
    end = parse_time(end_time, default=datetime.now(UTC))
    assert end is not None
    start = parse_time(start_time, default=end - timedelta(hours=default_hours))
    assert start is not None
    if start >= end:
        raise ValueError("start_time must be before end_time.")
    return start, end
