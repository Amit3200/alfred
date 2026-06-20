"""Resolve Slack user IDs to display names."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def pick_slack_display_name(user: dict) -> str:
    profile = user.get("profile") or {}
    display = (profile.get("display_name") or "").strip()
    if display:
        return display
    real = (profile.get("real_name") or user.get("real_name") or "").strip()
    if real:
        return real
    name = (user.get("name") or "").strip()
    if name:
        return name
    return user.get("id") or "unknown"


class SlackUserResolver:
    """Cache Slack users.info lookups for a single request."""

    def __init__(self, client: Any) -> None:
        self._client = client
        self._cache: dict[str, str] = {}

    def display_name(self, user_id: str) -> str:
        if not user_id:
            return "unknown"
        if user_id in self._cache:
            return self._cache[user_id]

        name = user_id
        try:
            response = self._client.users_info(user=user_id)
            if response.get("ok"):
                name = pick_slack_display_name(response.get("user") or {})
            else:
                logger.debug("users.info failed for %s: %s", user_id, response.get("error"))
        except Exception:
            logger.debug("users.info lookup failed for %s", user_id, exc_info=True)

        self._cache[user_id] = name
        return name

    def resolve_many(self, user_ids: set[str]) -> dict[str, str]:
        return {user_id: self.display_name(user_id) for user_id in user_ids}


def collect_reaction_user_ids(messages: list[dict]) -> set[str]:
    user_ids: set[str] = set()
    for message in messages:
        for reaction in message.get("reactions") or []:
            user_ids.update(reaction.get("users") or [])
    return user_ids


def format_user_list(user_ids: list[str], user_names: dict[str, str] | None = None) -> str:
    if user_names:
        return ", ".join(user_names.get(user_id, user_id) for user_id in user_ids)
    return ", ".join(user_ids)
