"""Resolve user IDs to human-readable display names for observability."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from backend.models.config import AlfredConfig

logger = logging.getLogger(__name__)

_SLACK_USER_RE = re.compile(r"^U[A-Z0-9]{6,}$")


def looks_like_slack_user_id(value: str) -> bool:
    return bool(_SLACK_USER_RE.match(value.strip()))


class UserLabelEnricher:
    """Map Slack IDs and internal keys to friendly names for dashboards."""

    def __init__(
        self,
        config: AlfredConfig,
        *,
        slack_client: Any | None = None,
        data_dir: Path | None = None,
    ) -> None:
        self._aliases = dict(getattr(config.observability, "user_labels", {}) or {})
        self._slack = slack_client
        self._cache: dict[str, str] = {}
        self._slack_preloaded = False
        self._user_cache = None
        if data_dir is not None:
            from backend.storage.slack_user_cache import SlackUserCache

            self._user_cache = SlackUserCache(data_dir)
            self._cache.update(self._user_cache.get_many())

    @classmethod
    def from_config(cls, config: AlfredConfig, *, data_dir: Path | None = None) -> "UserLabelEnricher":
        slack_client = None
        if config.slack.enabled and config.slack.bot_token:
            try:
                from slack_sdk import WebClient

                slack_client = WebClient(token=config.slack.bot_token)
            except Exception:
                slack_client = None
        enricher = cls(config, slack_client=slack_client, data_dir=data_dir)
        enricher.preload_slack_workspace()
        return enricher

    def preload_slack_workspace(self) -> None:
        """Load workspace members via users.list — more reliable than per-user lookups."""
        if self._slack_preloaded or self._slack is None:
            return
        self._slack_preloaded = True

        loaded = 0
        cursor: str | None = None
        try:
            while True:
                response = self._slack.users_list(limit=200, cursor=cursor)
                if not response.get("ok"):
                    logger.info(
                        "Slack users.list unavailable for name resolution: %s",
                        response.get("error"),
                    )
                    break
                from backend.ingress.slack_users import pick_slack_display_name

                for member in response.get("members") or []:
                    if member.get("deleted") or member.get("is_bot"):
                        continue
                    user_id = str(member.get("id") or "").strip()
                    if not user_id:
                        continue
                    name = pick_slack_display_name(member)
                    if name and name != user_id:
                        self._remember(user_id, name)
                        loaded += 1
                cursor = (response.get("response_metadata") or {}).get("next_cursor") or None
                if not cursor:
                    break
            if loaded:
                logger.info("Cached %d Slack user display names for observability", loaded)
        except Exception:
            logger.info("Slack users.list preload failed", exc_info=True)

    def display_name(self, user_id: str, user_label: str = "") -> str:
        uid = (user_id or "").strip()
        label = (user_label or "").strip()
        cache_key = uid or label
        if cache_key in self._cache:
            return self._cache[cache_key]

        for candidate in (uid, label):
            if candidate and candidate in self._aliases:
                self._cache[cache_key] = self._aliases[candidate]
                return self._aliases[candidate]

        if label and label not in {uid, "unknown"} and not looks_like_slack_user_id(label):
            self._cache[cache_key] = label
            return label

        slack_id = uid if looks_like_slack_user_id(uid) else label if looks_like_slack_user_id(label) else ""
        if slack_id and self._slack is not None:
            from backend.ingress.slack_users import SlackUserResolver

            resolved = SlackUserResolver(self._slack).display_name(slack_id)
            if resolved and resolved != slack_id:
                self._remember(slack_id, resolved)
                self._cache[cache_key] = resolved
                return resolved

        if uid == "admin-ui" or label == "admin-ui":
            self._cache[cache_key] = "Admin UI"
            return "Admin UI"
        if uid == "cli" or label == "cli":
            self._cache[cache_key] = "CLI"
            return "CLI"
        if label == "health-check":
            self._cache[cache_key] = "Health check"
            return "Health check"

        fallback = label or uid or "unknown"
        self._cache[cache_key] = fallback
        return fallback

    def enrich_event(self, event: dict[str, Any]) -> dict[str, Any]:
        uid = str(event.get("user_id") or "")
        label = str(event.get("user_label") or "")
        display = self.display_name(uid, label)
        enriched = dict(event)
        enriched["user_display_name"] = display
        enriched["user_label"] = display
        return enriched

    def merge_by_user(self, by_user: dict[str, int], rows: list[tuple[str, str, int]]) -> dict[str, int]:
        """Re-aggregate counts using display names when raw row data is available."""
        if rows:
            merged: dict[str, int] = {}
            for user_id, user_label, count in rows:
                name = self.display_name(user_id, user_label)
                merged[name] = merged.get(name, 0) + int(count)
            return dict(sorted(merged.items(), key=lambda item: (-item[1], item[0])))

        merged = {}
        for key, count in by_user.items():
            name = self.display_name(key, key)
            merged[name] = merged.get(name, 0) + int(count)
        return dict(sorted(merged.items(), key=lambda item: (-item[1], item[0])))

    def _remember(self, user_id: str, display_name: str) -> None:
        self._cache[user_id] = display_name
        if self._user_cache is not None:
            self._user_cache.remember(user_id, display_name)
