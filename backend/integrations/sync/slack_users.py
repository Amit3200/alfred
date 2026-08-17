"""Sync Slack workspace users into the local display-name cache."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from backend.db.slack_user_cache import SlackUserCache
from backend.integrations.identity.user_identity import list_slack_human_members
from backend.integrations.slack.users import pick_slack_display_name
from backend.integrations.sync.store import SyncStateStore
from backend.models.config import AlfredConfig

logger = logging.getLogger(__name__)


def _slack_client(config: AlfredConfig):
    if not config.slack.enabled or not config.slack.bot_token:
        return None
    try:
        from slack_sdk import WebClient

        return WebClient(token=config.slack.bot_token)
    except Exception:
        return None


def sync_slack_users(
    config: AlfredConfig,
    *,
    data_dir: Path | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Fetch Slack users.list and persist ID → display name mappings."""
    store = SyncStateStore(data_dir)
    refresh_hours = float(getattr(config.slack, "user_cache_refresh_hours", 1) or 1)
    if not force and not store.is_stale("slack_users", hours=refresh_hours):
        section = store.get("slack_users")
        return {
            "ok": True,
            "skipped": True,
            "reason": "cache_fresh",
            "user_count": int(section.get("user_count") or 0),
            "last_sync_at": section.get("last_sync_at"),
        }

    client = _slack_client(config)
    if client is None:
        return {"ok": False, "error": "Slack is not configured — enable Slack and set the bot token."}

    members, list_error = list_slack_human_members(client)
    if list_error:
        return {"ok": False, "error": list_error}
    if not members:
        return {"ok": False, "error": "No human Slack members found in the workspace."}

    mapping: dict[str, str] = {}
    for member in members:
        user_id = str(member.get("id") or "").strip()
        if not user_id:
            continue
        name = pick_slack_display_name(member)
        if name and name != user_id:
            mapping[user_id] = name

    cache = SlackUserCache(data_dir)
    cache.remember_many(mapping)

    section = store.update(
        "slack_users",
        {
            "user_count": len(mapping),
            "refresh_hours": refresh_hours,
        },
    )
    logger.info("Synced %d Slack users to local cache", len(mapping))
    return {
        "ok": True,
        "skipped": False,
        "user_count": len(mapping),
        "last_sync_at": section.get("last_sync_at"),
    }


def sync_slack_users_if_stale(config: AlfredConfig, *, data_dir: Path | None = None) -> None:
    """Background-friendly refresh used by observability and ingress."""
    try:
        sync_slack_users(config, data_dir=data_dir, force=False)
    except Exception:
        logger.info("Slack user cache refresh failed", exc_info=True)
