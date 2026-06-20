"""Fetch Slack thread + channel history for Alfred context."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.ingress.context_policy import wants_channel_history
from backend.ingress.slack_messages import format_slack_message
from backend.models.task import Task
from backend.ingress.slack_users import SlackUserResolver, collect_reaction_user_ids

logger = logging.getLogger(__name__)

# Default channel history depth for Alfred (UTC).
CHANNEL_HISTORY_DAYS = 30


@dataclass
class SlackContextBundle:
    text: str
    channel_messages: list[dict] = field(default_factory=list)
    thread_messages: list[dict] = field(default_factory=list)
    history_window_label: str = ""
    user_names: dict[str, str] = field(default_factory=dict)


def parse_history_window(
    intent: str,
    *,
    now: datetime | None = None,
) -> tuple[str | None, str | None, str, int]:
    """Return (oldest_ts, latest_ts, label, limit) for conversations.history."""
    now = now or datetime.now(timezone.utc)
    lower = intent.lower()

    if "yesterday" in lower:
        day = (now - timedelta(days=1)).date()
        start = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)
        end = start + timedelta(days=1)
        return str(start.timestamp()), str(end.timestamp()), "yesterday (UTC)", 200

    if "today" in lower:
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return str(start.timestamp()), str(now.timestamp()), "today (UTC)", 200

    start = now - timedelta(days=CHANNEL_HISTORY_DAYS)
    return (
        str(start.timestamp()),
        str(now.timestamp()),
        f"last {CHANNEL_HISTORY_DAYS} days",
        200,
    )


def fetch_slack_context(
    client: Any,
    task: Task,
    *,
    bot_user_id: str = "",
) -> SlackContextBundle:
    """Load thread and/or channel messages based on the user's question."""
    if not task.channel_id:
        return SlackContextBundle(text="")

    in_thread = bool(task.metadata.get("in_existing_thread"))
    intent = task.cleaned_intent
    sections: list[str] = []
    channel_messages: list[dict] = []
    history_window_label = ""
    thread_messages: list[dict] = []
    user_names: dict[str, str] = {}

    if wants_channel_history(intent, in_existing_thread=in_thread):
        oldest, latest, label, limit = parse_history_window(intent)
        history_window_label = label
        channel_messages = fetch_channel_messages(
            client,
            task.channel_id,
            oldest=oldest,
            latest=latest,
            limit=limit,
            bot_user_id=bot_user_id,
        )

    if in_thread or "thread" in intent.lower():
        thread_messages = fetch_thread_messages(
            client,
            task,
            bot_user_id=bot_user_id,
        )

    if channel_messages or thread_messages:
        user_names = _resolve_user_names(client, channel_messages + thread_messages)

    if wants_channel_history(intent, in_existing_thread=in_thread):
        label = history_window_label
        channel_text = messages_to_text(channel_messages, user_names=user_names)
        if channel_text:
            sections.append(f"Channel messages ({label}, oldest → newest):\n{channel_text}")
            logger.info(
                "Channel history: %d chars (%s) task=%s channel=%s",
                len(channel_text),
                label,
                task.id,
                task.channel_id,
            )
        else:
            sections.append(
                f"Channel messages ({label}): none returned — the answer may be outside this window."
            )

    if in_thread or "thread" in intent.lower():
        thread_text = messages_to_text(thread_messages, user_names=user_names)
        if thread_text:
            sections.append(f"Thread messages (oldest → newest):\n{thread_text}")
            logger.debug("Thread context loaded (%d chars) for task %s", len(thread_text), task.id)

    return SlackContextBundle(
        text="\n\n".join(sections) if sections else "",
        channel_messages=channel_messages,
        thread_messages=thread_messages,
        history_window_label=history_window_label,
        user_names=user_names,
    )


def fetch_channel_history(
    client: Any,
    channel_id: str,
    *,
    oldest: str | None = None,
    latest: str | None = None,
    limit: int = 100,
    bot_user_id: str = "",
) -> str | None:
    messages = fetch_channel_messages(
        client,
        channel_id,
        oldest=oldest,
        latest=latest,
        limit=limit,
        bot_user_id=bot_user_id,
    )
    return messages_to_text(messages)


def fetch_channel_messages(
    client: Any,
    channel_id: str,
    *,
    oldest: str | None = None,
    latest: str | None = None,
    limit: int = 100,
    bot_user_id: str = "",
) -> list[dict]:
    kwargs: dict[str, Any] = {"channel": channel_id, "limit": min(limit, 200)}
    if oldest:
        kwargs["oldest"] = oldest
    if latest:
        kwargs["latest"] = latest
    try:
        response = client.conversations_history(**kwargs)
    except Exception as exc:
        raise RuntimeError(_slack_scope_hint(str(exc))) from exc
    if not response.get("ok"):
        error = response.get("error", "unknown")
        if error == "missing_scope":
            needed = response.get("needed", "groups:history")
            raise RuntimeError(
                f"Slack bot is missing scope `{needed}`. "
                "Add it under OAuth & Permissions → Bot Token Scopes, reinstall the app, "
                "then restart Alfred."
            )
        logger.warning("Slack messages API error: %s", error)
        return []
    messages = list(response.get("messages", []))
    messages.reverse()
    return [m for m in messages if not _should_skip_message(m, bot_user_id=bot_user_id)]


def messages_to_text(
    messages: list[dict],
    *,
    user_names: dict[str, str] | None = None,
) -> str | None:
    lines: list[str] = []
    for index, message in enumerate(messages, start=1):
        line = format_slack_message(message, user_names=user_names)
        if line:
            lines.append(f"[{index}] {line}")
    return "\n".join(lines) if lines else None


def fetch_thread_messages(
    client: Any,
    task: Task,
    *,
    limit: int = 50,
    bot_user_id: str = "",
) -> list[dict]:
    if not task.channel_id or not task.thread_ts:
        return []
    try:
        response = client.conversations_replies(
            channel=task.channel_id,
            ts=task.thread_ts,
            limit=limit,
        )
    except Exception as exc:
        raise RuntimeError(_slack_scope_hint(str(exc))) from exc
    if not response.get("ok"):
        error = response.get("error", "unknown")
        if error == "missing_scope":
            needed = response.get("needed", "groups:history")
            raise RuntimeError(
                f"Slack bot is missing scope `{needed}`. "
                "Add it under OAuth & Permissions → Bot Token Scopes, reinstall the app, "
                "then restart Alfred."
            )
        logger.warning("Slack messages API error: %s", error)
        return []
    messages = list(response.get("messages", []))
    return [m for m in messages if not _should_skip_message(m, bot_user_id=bot_user_id)]


def fetch_thread_replies(
    client: Any,
    task: Task,
    *,
    limit: int = 50,
    bot_user_id: str = "",
) -> str | None:
    messages = fetch_thread_messages(
        client,
        task,
        limit=limit,
        bot_user_id=bot_user_id,
    )
    return messages_to_text(messages)


def _resolve_user_names(client: Any, messages: list[dict]) -> dict[str, str]:
    user_ids = collect_reaction_user_ids(messages)
    if not user_ids:
        return {}
    return SlackUserResolver(client).resolve_many(user_ids)


def _slack_scope_hint(error_text: str) -> str:
    if "groups:history" in error_text:
        return (
            "Cannot read this private channel — add Bot scope `groups:history` "
            "(and `groups:read`), reinstall the Slack app, then restart Alfred."
        )
    if "missing_scope" in error_text:
        return f"Slack scope error: {error_text}. Add the missing scope and reinstall the app."
    return error_text


def _should_skip_message(message: dict, *, bot_user_id: str) -> bool:
    """Skip Alfred's own posts; keep other bots (alert integrations)."""
    if bot_user_id and message.get("user") == bot_user_id:
        return True
    text = (message.get("text") or "").lower()
    if message.get("bot_id") and "alfred" in (message.get("username") or "").lower():
        return True
    if bot_user_id and f"<@{bot_user_id}>" in text and message.get("bot_id"):
        return True
    return False
