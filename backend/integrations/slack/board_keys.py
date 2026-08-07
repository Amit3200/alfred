"""Helpers for per-channel Slack board registry keys."""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


def derive_board_key(*, channel_name: str = "", channel_id: str = "") -> str:
    """Build a stable registry key for a channel's board binding."""
    raw = (channel_name or "").strip().lstrip("#")
    slug = re.sub(r"[^a-z0-9]+", "-", raw.lower()).strip("-")
    if slug:
        return slug[:40]
    cid = re.sub(r"[^a-z0-9]", "", (channel_id or "").lower())
    if cid:
        return f"board-{cid[-8:]}"
    return "board"


def fetch_slack_channel_name(config: Any, channel_id: str) -> str:
    """Best-effort Slack channel name lookup for board key derivation."""
    token = str(getattr(getattr(config, "slack", None), "bot_token", "") or "").strip()
    if not token or not channel_id:
        return ""
    try:
        from slack_sdk import WebClient

        client = WebClient(token=token)
        response = client.conversations_info(channel=channel_id)
        channel = response.get("channel") or {}
        return str(channel.get("name") or "")
    except Exception as exc:
        logger.debug("Could not fetch Slack channel name for %s: %s", channel_id, exc)
        return ""
