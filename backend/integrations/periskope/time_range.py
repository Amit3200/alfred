"""Parse natural-language dates for Periskope message queries."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

_ISO_DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2})(?:T[\d:+.Z-]+)?\b")
_ORDINAL_DATE = re.compile(
    r"\b(\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
    r"(?:\s+(\d{4}))?\b",
    re.I,
)
_TODAY_RE = re.compile(r"\b(today|todays)\b", re.I)
_YESTERDAY_RE = re.compile(r"\byesterday\b", re.I)
_LAST_N_WEEKS = re.compile(r"\b(?:last|past|previous)\s+(\d+)\s+weeks?\b", re.I)
_LAST_WEEK = re.compile(r"\b(?:last|past|previous)\s+week\b", re.I)
_LAST_N_DAYS = re.compile(r"\b(?:last|past|previous)\s+(\d+)\s+days?\b", re.I)

_MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}


def _tz(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name or "Asia/Kolkata")
    except Exception:
        return ZoneInfo("Asia/Kolkata")


def _parse_day(text: str, *, now: datetime) -> datetime | None:
    iso = _ISO_DATE.search(text or "")
    if iso:
        parsed = datetime.fromisoformat(iso.group(1)).replace(tzinfo=now.tzinfo)
        return parsed
    if _TODAY_RE.search(text or ""):
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if _YESTERDAY_RE.search(text or ""):
        day = now - timedelta(days=1)
        return day.replace(hour=0, minute=0, second=0, microsecond=0)
    match = _ORDINAL_DATE.search(text or "")
    if not match:
        return None
    day = int(match.group(1))
    month = _MONTHS[match.group(2).lower()]
    year = int(match.group(3) or now.year)
    try:
        return datetime(year, month, day, tzinfo=now.tzinfo)
    except ValueError:
        return None


def _parse_relative_range(text: str, *, now: datetime) -> tuple[datetime, datetime] | None:
    raw = text or ""
    weeks = _LAST_N_WEEKS.search(raw)
    if weeks:
        days = 7 * max(1, int(weeks.group(1)))
        start = (now - timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)
        return start, now
    if _LAST_WEEK.search(raw):
        start = (now - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
        return start, now
    days_match = _LAST_N_DAYS.search(raw)
    if days_match:
        days = max(1, int(days_match.group(1)))
        start = (now - timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)
        return start, now
    return None


def looks_like_date_window(text: str) -> bool:
    raw = text or ""
    return bool(
        _ISO_DATE.search(raw)
        or _ORDINAL_DATE.search(raw)
        or _TODAY_RE.search(raw)
        or _YESTERDAY_RE.search(raw)
        or _LAST_N_WEEKS.search(raw)
        or _LAST_WEEK.search(raw)
        or _LAST_N_DAYS.search(raw)
    )


def periskope_start(value: datetime) -> str:
    return value.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()


def periskope_end(value: datetime, *, now: datetime) -> str:
    """Periskope date-only end_time is midnight, so a same-day YYYY-MM-DD window is empty.

    Docs show end examples like ``2025-04-25T23:59:59Z``. Use end-of-day for past
    days and "now" when the window includes today.
    """
    if value.date() < now.date():
        return value.replace(hour=23, minute=59, second=59, microsecond=0).isoformat()
    return now.replace(microsecond=0).isoformat()


def resolve_message_window(
    start_time: str = "",
    end_time: str = "",
    *,
    intent: str = "",
    timezone: str = "Asia/Kolkata",
    now: datetime | None = None,
) -> tuple[str, str]:
    """Return (start_time, end_time) as timezone-aware ISO strings Periskope accepts.

    Empty strings mean "do not send that filter".
    """
    zone = _tz(timezone)
    current = now.astimezone(zone) if now is not None else datetime.now(zone)
    combined = " ".join(part for part in (start_time, end_time, intent) if part).strip()
    relative = _parse_relative_range(combined, now=current)
    if relative and not _parse_day(start_time, now=current) and not _parse_day(end_time, now=current):
        start, end = relative
        return periskope_start(start), periskope_end(end, now=current)
    start = _parse_day(start_time, now=current) or _parse_day(combined, now=current)
    end = _parse_day(end_time, now=current)
    if start is None and end is None:
        return "", ""
    if start is None:
        start = end
    if end is None:
        if start.date() < current.date():
            end = start
        else:
            end = current
    if start > end:
        start, end = end, start
    return periskope_start(start), periskope_end(end, now=current)
