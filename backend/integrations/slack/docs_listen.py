"""Decide whether an unmentioned Slack channel message should run docs search."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from backend.integrations.slack.sanitize import channel_allowed, clean_slack_text
from backend.models.config import SlackConfig
from backend.routing.channel_settings import (
    channel_docs_search_enabled,
    is_channel_write_or_admin_intent,
)

_TRIVIAL_RE = re.compile(
    r"^(ok(ay)?|thanks?|thx|ty|np|yes|no|\+1|done|k|lol|lgtm|hmm+|hi|hello|hey|👍|🙏|✅)\.?$",
    re.I,
)
_IGNORED_SUBTYPES = frozenset(
    {
        "bot_message",
        "message_changed",
        "message_deleted",
        "channel_join",
        "channel_leave",
        "channel_topic",
        "channel_purpose",
        "channel_name",
        "channel_archive",
        "channel_unarchive",
        "group_join",
        "group_leave",
        "ekm_access_denied",
        "thread_broadcast",
        "reply_broadcast",
    }
)


def _mentions_bot(event: dict[str, Any], bot_user_id: str) -> bool:
    if not bot_user_id:
        return False
    text = event.get("text") or ""
    return f"<@{bot_user_id}>" in text


def should_handle_docs_search_message(
    event: dict[str, Any],
    *,
    bot_user_id: str,
    slack_config: SlackConfig,
    data_dir: Path | None,
) -> bool:
    """True for human channel messages that should run docs Q&A without @mention."""
    if data_dir is None:
        return False
    if event.get("bot_id") or event.get("bot_profile"):
        return False
    subtype = event.get("subtype")
    if subtype in _IGNORED_SUBTYPES:
        return False
    if subtype not in (None, "", "file_share"):
        return False
    if event.get("hidden"):
        return False
    channel_type = str(event.get("channel_type") or "")
    if channel_type in ("im", "mpim"):
        return False
    user = str(event.get("user") or "")
    if not user:
        return False
    if bot_user_id and user == bot_user_id:
        return False
    if _mentions_bot(event, bot_user_id):
        return False
    channel_id = str(event.get("channel") or "")
    if not channel_id or not channel_allowed(channel_id, slack_config):
        return False
    if not channel_docs_search_enabled(data_dir, channel_id):
        return False
    cleaned = clean_slack_text(event.get("text") or "")
    if not cleaned or _TRIVIAL_RE.match(cleaned.strip()):
        return False
    if is_channel_write_or_admin_intent(cleaned):
        return False
    try:
        from backend.formatting.slack_lists import extract_embedded_list_records

        if extract_embedded_list_records([event]):
            return False
    except Exception:
        pass
    return True
