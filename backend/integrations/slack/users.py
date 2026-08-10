"""Resolve Slack user IDs to display names."""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_SLACK_USER_ID_RE = re.compile(r"\b(U[A-Z0-9]{8,})\b")
_SLACK_MENTION_RE = re.compile(r"<@(U[A-Z0-9]{8,})>")


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
    return collect_message_user_ids(messages)


def collect_message_user_ids(messages: list[dict]) -> set[str]:
    """Collect Slack user IDs from message authors and reactions."""
    user_ids: set[str] = set()
    for message in messages:
        author = message.get("user")
        if author:
            user_ids.add(str(author))
        for reaction in message.get("reactions") or []:
            user_ids.update(str(user_id) for user_id in (reaction.get("users") or []))
    return user_ids


def format_user_id_legend(user_names: dict[str, str]) -> str:
    if not user_names:
        return ""
    lines = ["Slack user names (use these names in your reply — not raw IDs):"]
    for user_id, name in sorted(user_names.items(), key=lambda item: item[1].lower()):
        lines.append(f"- {name} ({user_id})")
    return "\n".join(lines)


def substitute_slack_user_ids(text: str, user_names: dict[str, str]) -> str:
    if not text or not user_names:
        return text

    def mention_repl(match: re.Match[str]) -> str:
        user_id = match.group(1)
        return user_names.get(user_id, user_id)

    def id_repl(match: re.Match[str]) -> str:
        user_id = match.group(1)
        return user_names.get(user_id, user_id)

    text = _SLACK_MENTION_RE.sub(mention_repl, text)
    return _SLACK_USER_ID_RE.sub(id_repl, text)


def substitute_slack_user_ids_as_mentions(text: str, user_names: dict[str, str]) -> str:
    """Replace Slack user ids with @DisplayName for human-readable ticket details."""
    if not text or not user_names:
        return text

    def as_mention(user_id: str) -> str:
        name = (user_names.get(user_id) or "").strip()
        if not name or name == user_id:
            return user_id
        return f"@{name}"

    def mention_repl(match: re.Match[str]) -> str:
        return as_mention(match.group(1))

    def id_repl(match: re.Match[str]) -> str:
        return as_mention(match.group(1))

    text = _SLACK_MENTION_RE.sub(mention_repl, text)
    return _SLACK_USER_ID_RE.sub(id_repl, text)


def resolve_user_ids_in_text(text: str, resolver: SlackUserResolver) -> str:
    if not text:
        return text
    user_ids = set(_SLACK_USER_ID_RE.findall(text))
    user_ids.update(_SLACK_MENTION_RE.findall(text))
    if not user_ids:
        return text
    return substitute_slack_user_ids(text, resolver.resolve_many(user_ids))


def format_user_list(user_ids: list[str], user_names: dict[str, str] | None = None) -> str:
    if user_names:
        return ", ".join(user_names.get(user_id, user_id) for user_id in user_ids)
    return ", ".join(user_ids)
