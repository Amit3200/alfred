"""Slack List board field defaults and ticket-detail formatting.

Domain-owned so tools and integrations never import routing for these helpers.
"""

from __future__ import annotations

import re
from typing import Any

_SEVERITY_ALIASES = {
    "p0": "High",
    "p1": "High",
    "p2": "Medium",
    "p3": "Low",
    "high": "High",
    "medium": "Medium",
    "low": "Low",
    "critical": "High",
    "urgent": "High",
}

DEFAULT_BOARD_SEVERITY = "Medium"

_WEAK_TITLE_PHRASES = frozenset(
    {
        "the same",
        "for the same",
        "same",
        "it",
        "this",
        "that",
        "to call me",
        "call me",
        "do the needful",
        "the needful",
        "for above",
        "above",
        "for the above",
        "the above",
        "the above?",
        "needful",
    }
)

_BOARD_NOISE_PATTERNS = (
    "created and linked slack list",
    "setup board",
    "board key:",
    "display prefix:",
    "what should the task be called",
    "linked this channel to slack list",
    "show board config",
)


def normalize_board_severity(raw: str) -> str:
    """Map P0/P1/priority wording to Slack List Severity labels (High/Medium/Low)."""
    key = (raw or "").strip().lower()
    if not key:
        return ""
    if key in _SEVERITY_ALIASES:
        return _SEVERITY_ALIASES[key]
    for label in ("high", "medium", "low"):
        if label in key:
            return label.title()
    titled = raw.strip().title()
    return titled if titled in ("High", "Medium", "Low") else ""


def finalize_board_create_fields(
    *,
    severity: str = "",
    assignee_user_id: str = "",
    requester_user_id: str = "",
    bot_user_id: str = "",
    default_assignee_to_requester: bool = True,
) -> dict[str, str]:
    """Apply create defaults: Medium severity; optional requester assignee when none was parsed."""
    sev = normalize_board_severity(severity) or DEFAULT_BOARD_SEVERITY
    assignee = (assignee_user_id or "").strip()
    requester = (requester_user_id or "").strip()
    bot = (bot_user_id or "").strip()
    if (
        not assignee
        and default_assignee_to_requester
        and requester
        and requester != bot
    ):
        assignee = requester
    return {"severity": sev, "assignee_user_id": assignee}


def is_weak_board_task_title(title: str) -> bool:
    """True when a parsed title is a command fragment, not real work."""
    cleaned = re.sub(r"\s+", " ", (title or "").strip().lower())
    cleaned = cleaned.strip("?!.")
    if not cleaned or len(cleaned) < 4:
        return True
    if cleaned in _WEAK_TITLE_PHRASES:
        return True
    if cleaned in ("above", "the above", "for above", "for the above"):
        return True
    if cleaned.startswith("to ") and len(cleaned.split()) <= 4:
        return True
    if re.fullmatch(r"(?:for|on|to)\s+\w+(?:\s+\w+){0,2}", cleaned):
        return True
    return False


def slack_thread_permalink(
    *,
    channel_id: str,
    thread_ts: str,
    team_id: str = "",
) -> str:
    cid = (channel_id or "").strip()
    ts = (thread_ts or "").strip()
    if not cid or not ts:
        return ""
    ts_link = ts.replace(".", "")
    tid = (team_id or "").strip()
    if tid:
        return f"https://app.slack.com/client/{tid}/{cid}/thread/{cid}-{ts_link}"
    return f"https://slack.com/archives/{cid}/p{ts_link}"


def _is_board_noise(text: str) -> bool:
    lower = (text or "").lower()
    return any(pattern in lower for pattern in _BOARD_NOISE_PATTERNS)


def _line_message_body(line: str) -> str:
    stripped = (line or "").strip()
    if not stripped:
        return ""
    match = re.match(r"^\[\d+\]\s+[^|]+\|\s*(?:[^:]+:\s*)?(.*)$", stripped)
    return (match.group(1) if match else stripped).strip()


def humanize_board_task_text(text: str, mention_labels: dict[str, str]) -> str:
    """Use @DisplayName instead of raw U… ids in ticket details."""
    from backend.integrations.slack.users import substitute_slack_user_ids_as_mentions

    return substitute_slack_user_ids_as_mentions(text, mention_labels)


def build_board_task_details(
    *,
    messages_text: str = "",
    channel_id: str = "",
    thread_ts: str = "",
    team_id: str = "",
    task_title: str = "",
    bot_user_id: str = "",
    requester_user_id: str = "",
    mention_labels: dict[str, str] | None = None,
    max_chars: int = 2000,
) -> str:
    """Structured ticket details: short summary, Slack thread link, key points — not raw logs."""
    thread_url = slack_thread_permalink(
        channel_id=channel_id,
        thread_ts=thread_ts,
        team_id=team_id,
    )
    user_points: list[str] = []
    for line in (messages_text or "").splitlines():
        body = _line_message_body(line)
        if not body or _is_board_noise(body):
            continue
        if bot_user_id and f"bot (app):" in line.lower() and bot_user_id not in line:
            continue
        if body not in user_points:
            user_points.append(body[:400])

    summary = (task_title or "").strip()
    if is_weak_board_task_title(summary):
        summary = ""
    if not summary and user_points:
        summary = user_points[0][:200]
    if not summary:
        summary = "Task created from Slack"

    parts = [f"Summary: {summary}"]
    if thread_url:
        parts.append(f"Slack thread: {thread_url}")
    extra = [p for p in user_points if p != summary][:3]
    if extra:
        parts.append("Context:")
        parts.extend(f"• {point[:240]}" for point in extra)
    requester = (requester_user_id or "").strip()
    if requester:
        labels = mention_labels or {}
        name = labels.get(requester, "").strip()
        parts.append(f"Requested by: @{name}" if name else f"Requested by: {requester}")

    body = "\n".join(parts)
    body = humanize_board_task_text(body, mention_labels or {})
    if len(body) > max_chars:
        return body[: max_chars - 20] + "\n… (truncated)"
    return body
