"""Slack read tool handlers."""

from __future__ import annotations

from typing import Any

from backend.integrations.slack.context import (
    fetch_channel_messages,
    fetch_thread_messages,
    messages_to_text,
    parse_history_window,
)
from backend.models.config import AlfredConfig
from backend.models.task import Task
from backend.tools.registry import ToolRegistry
from backend.tools.result import ToolResult
from backend.tools.slack.schemas import SLACK_FETCH_CHANNEL_HISTORY, SLACK_FETCH_THREAD


def register_slack_tools(
    registry: ToolRegistry,
    config: AlfredConfig,
    *,
    default_task: Task | None = None,
) -> None:
    if not config.slack.enabled:
        return
    token = (config.slack.bot_token or "").strip()
    if not token:
        return

    from slack_sdk import WebClient

    client = WebClient(token=token)
    bot_user_id = _bot_user_id(client)
    task = default_task

    def _task_from_args(args: dict[str, Any]) -> Task | None:
        if task is not None:
            return task
        channel_id = str(args.get("channel_id") or "").strip()
        thread_ts = str(args.get("thread_ts") or "").strip()
        if not channel_id:
            return None
        return Task(
            source="slack",
            user_id="",
            channel_id=channel_id,
            thread_ts=thread_ts,
            raw_text="",
            cleaned_intent="",
        )

    def fetch_thread_handler(args: dict[str, Any]) -> ToolResult:
        current = getattr(registry, "current_task", None) or _task_from_args(args)
        if current is None or not current.channel_id or not current.thread_ts:
            return ToolResult.error(
                "slack_fetch_thread requires an active Slack thread (channel_id + thread_ts)."
            )
        limit = min(int(args.get("limit") or 50), 100)
        try:
            messages = fetch_thread_messages(
                client,
                current,
                limit=limit,
                bot_user_id=bot_user_id,
            )
            text = messages_to_text(messages) or ""
            return ToolResult(
                kind="slack_messages",
                data={
                    "source": "thread",
                    "channel_id": current.channel_id,
                    "thread_ts": current.thread_ts,
                    "message_count": len(messages),
                    "text": text,
                },
            )
        except Exception as exc:
            return ToolResult.error(str(exc))

    def fetch_history_handler(args: dict[str, Any]) -> ToolResult:
        current = getattr(registry, "current_task", None) or _task_from_args(args)
        if current is None or not current.channel_id:
            return ToolResult.error("slack_fetch_channel_history requires channel_id.")
        intent = current.cleaned_intent or "last 7 days"
        if args.get("days"):
            intent = f"last {int(args['days'])} days"
        oldest, latest, label, default_limit = parse_history_window(intent)
        limit = min(int(args.get("limit") or default_limit), 200)
        try:
            messages = fetch_channel_messages(
                client,
                current.channel_id,
                oldest=oldest,
                latest=latest,
                limit=limit,
                bot_user_id=bot_user_id,
            )
            text = messages_to_text(messages) or ""
            return ToolResult(
                kind="slack_messages",
                data={
                    "source": "channel_history",
                    "channel_id": current.channel_id,
                    "window": label,
                    "message_count": len(messages),
                    "text": text,
                },
            )
        except Exception as exc:
            return ToolResult.error(str(exc))

    registry.register(SLACK_FETCH_THREAD, fetch_thread_handler)
    registry.register(SLACK_FETCH_CHANNEL_HISTORY, fetch_history_handler)


def _bot_user_id(client: Any) -> str:
    try:
        auth = client.auth_test()
        return str(auth.get("user_id") or "")
    except Exception:
        return ""
