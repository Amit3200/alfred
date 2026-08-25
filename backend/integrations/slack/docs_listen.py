"""Decide whether an unmentioned Slack channel message should run docs search."""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Callable

from backend.db.slack_workflows_db import db_list_board_bindings
from backend.integrations.slack.sanitize import channel_allowed, clean_slack_text
from backend.models.config import SlackConfig
from backend.routing.channel_settings import (
    channel_docs_search_enabled,
    is_channel_write_or_admin_intent,
)

logger = logging.getLogger(__name__)

POLL_INTERVAL_SEC = 5.0
FIRST_LOOKBACK_SEC = 2 * 60 * 60
_CURSORS_NAME = "docs_search_cursors.json"

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


def docs_search_channels(data_dir: Path | None) -> list[dict[str, Any]]:
    if data_dir is None:
        return []
    return [
        row
        for row in db_list_board_bindings(data_dir)
        if row.get("enabled") and row.get("docs_search_enabled") and row.get("channel_id")
    ]


def history_event(channel_id: str, message: dict[str, Any]) -> dict[str, Any]:
    event = dict(message)
    event["channel"] = channel_id
    event.setdefault("channel_type", "channel")
    event.setdefault("type", "message")
    return event


def _cursors_path(data_dir: Path) -> Path:
    return Path(data_dir) / _CURSORS_NAME


def _load_cursors(data_dir: Path) -> dict[str, Any]:
    path = _cursors_path(data_dir)
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _save_cursors(data_dir: Path, data: dict[str, Any]) -> None:
    path = _cursors_path(data_dir)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def already_seen(data_dir: Path, channel_id: str, ts: str) -> bool:
    if not ts:
        return False
    entry = _load_cursors(data_dir).get(channel_id) or {}
    seen = entry.get("seen") or []
    return ts in seen


def mark_seen(data_dir: Path, channel_id: str, ts: str) -> None:
    if not ts:
        return
    data = _load_cursors(data_dir)
    entry = dict(data.get(channel_id) or {})
    seen = [str(item) for item in (entry.get("seen") or []) if item]
    if ts not in seen:
        seen.append(ts)
    entry["seen"] = seen[-80:]
    if not entry.get("oldest") or float(ts) > float(entry.get("oldest") or 0):
        entry["oldest"] = ts
    data[channel_id] = entry
    _save_cursors(data_dir, data)


def poll_docs_search_once(
    client: Any,
    *,
    slack_config: SlackConfig,
    data_dir: Path,
    bot_user_id: str,
    on_event: Callable[[dict[str, Any]], None],
    now: float | None = None,
) -> int:
    """Fetch new channel messages and pass docs-search hits to on_event."""
    handled = 0
    now = time.time() if now is None else now
    cursors = _load_cursors(data_dir)
    for row in docs_search_channels(data_dir):
        channel_id = str(row.get("channel_id") or "")
        entry = dict(cursors.get(channel_id) or {})
        oldest = str(entry.get("oldest") or "")
        bootstrap = not oldest
        if bootstrap:
            oldest = f"{now - FIRST_LOOKBACK_SEC:.6f}"
        try:
            response = client.conversations_history(
                channel=channel_id,
                oldest=oldest,
                inclusive=False,
                limit=20,
            )
        except Exception:
            logger.exception("Docs-search poll failed channel=%s", channel_id)
            continue
        messages = list(response.get("messages") or [])
        messages.reverse()
        latest = oldest
        for message in messages:
            if not isinstance(message, dict):
                continue
            ts = str(message.get("ts") or "")
            if ts:
                latest = ts
            if already_seen(data_dir, channel_id, ts):
                continue
            event = history_event(channel_id, message)
            if not should_handle_docs_search_message(
                event,
                bot_user_id=bot_user_id,
                slack_config=slack_config,
                data_dir=data_dir,
            ):
                if ts:
                    mark_seen(data_dir, channel_id, ts)
                continue
            logger.info(
                "docs_search poll hit channel=%s ts=%s text=%r",
                channel_id,
                ts,
                str(event.get("text") or "")[:120],
            )
            on_event(event)
            mark_seen(data_dir, channel_id, ts)
            handled += 1
        if latest:
            persisted = dict(_load_cursors(data_dir).get(channel_id) or {})
            persisted["oldest"] = latest
            if persisted.get("seen") is None and entry.get("seen"):
                persisted["seen"] = entry["seen"]
            cursors[channel_id] = persisted
            _save_cursors(data_dir, cursors)
        elif bootstrap:
            persisted = dict(_load_cursors(data_dir).get(channel_id) or {})
            persisted["oldest"] = f"{now:.6f}"
            cursors[channel_id] = persisted
            _save_cursors(data_dir, cursors)
    return handled
