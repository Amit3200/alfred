"""Event sanitizer — strip bot mentions and build Task objects."""

from __future__ import annotations

import re

from backend.models.config import SlackConfig
from backend.models.task import Task

_MENTION_RE = re.compile(r"<@[A-Z0-9]+>\s*")
_ALFRED_PREFIX_RE = re.compile(r"^@?alfred[,:]?\s+", re.IGNORECASE)


def channel_allowed(channel_id: str, slack_config: SlackConfig) -> bool:
    allowed = slack_config.allowed_channels or ["*"]
    if "*" in allowed:
        return True
    normalized = {entry.strip().lstrip("#") for entry in allowed if entry.strip()}
    return channel_id in normalized


def clean_slack_text(raw_text: str) -> str:
    text = _MENTION_RE.sub("", raw_text or "").strip()
    text = _ALFRED_PREFIX_RE.sub("", text).strip()
    return text


def sanitize_slack_mention(event: dict, slack_config: SlackConfig) -> Task | None:
    channel_id = event.get("channel") or ""
    if not channel_allowed(channel_id, slack_config):
        return None

    raw_text = event.get("text") or ""
    cleaned = clean_slack_text(raw_text)
    if not cleaned:
        return None

    thread_ts = event.get("thread_ts") or event.get("ts")
    in_existing_thread = bool(event.get("thread_ts"))
    return Task(
        source="slack",
        user_id=event.get("user") or "",
        channel_id=channel_id,
        thread_ts=thread_ts,
        raw_text=raw_text,
        cleaned_intent=cleaned,
        metadata={
            "event_ts": event.get("ts"),
            "team": event.get("team"),
            "in_existing_thread": in_existing_thread,
        },
    )
