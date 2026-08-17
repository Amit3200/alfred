"""Slack read FunctionTools."""

from __future__ import annotations

from typing import Any

from backend.integrations.slack.context import (
    fetch_channel_messages,
    fetch_thread_messages,
    messages_to_text,
    parse_history_window,
)
from backend.models.task import Task
from backend.tools.base.function_tool import FunctionTool
from backend.tools.base.tool import BaseTool, ToolContext
from backend.tools.result import ToolResult
from backend.tools.slack.schemas import SLACK_FETCH_CHANNEL_HISTORY, SLACK_FETCH_THREAD


def _bot_user_id(client: Any) -> str:
    try:
        auth = client.auth_test()
        return str(auth.get("user_id") or "")
    except Exception:
        return ""


def _client(ctx: ToolContext) -> Any:
    from slack_sdk import WebClient

    token = (ctx.config.slack.bot_token or "").strip()
    return WebClient(token=token)


def _task_from_ctx(ctx: ToolContext, args: dict[str, Any]) -> Task | None:
    registry = ctx.get("registry")
    current = getattr(registry, "current_task", None) if registry is not None else None
    if current is not None:
        return current
    default_task = ctx.get("default_task")
    if default_task is not None:
        return default_task
    if ctx.channel_id:
        return Task(
            source="slack",
            user_id=ctx.user_id or "",
            channel_id=ctx.channel_id,
            thread_ts=ctx.thread_ts or "",
            raw_text="",
            cleaned_intent="",
        )
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


def slack_fetch_thread(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    current = _task_from_ctx(ctx, args)
    if current is None or not current.channel_id or not current.thread_ts:
        return ToolResult.error(
            "slack_fetch_thread requires an active Slack thread (channel_id + thread_ts)."
        )
    limit = min(int(args.get("limit") or 50), 100)
    client = _client(ctx)
    try:
        messages = fetch_thread_messages(
            client,
            current,
            limit=limit,
            bot_user_id=_bot_user_id(client),
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


def slack_fetch_channel_history(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    current = _task_from_ctx(ctx, args)
    if current is None or not current.channel_id:
        return ToolResult.error("slack_fetch_channel_history requires channel_id.")
    intent = current.cleaned_intent or "last 7 days"
    if args.get("days"):
        intent = f"last {int(args['days'])} days"
    oldest, latest, label, default_limit = parse_history_window(intent)
    limit = min(int(args.get("limit") or default_limit), 200)
    client = _client(ctx)
    try:
        messages = fetch_channel_messages(
            client,
            current.channel_id,
            oldest=oldest,
            latest=latest,
            limit=limit,
            bot_user_id=_bot_user_id(client),
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


def slack_read_tools() -> list[BaseTool]:
    return [
        FunctionTool(
            name="slack_fetch_thread",
            capability="slack.read.thread",
            operation="fetch_thread",
            domain="slack",
            schema=SLACK_FETCH_THREAD,
            run_fn=slack_fetch_thread,
            produces=("thread_text",),
            next_tools=("slack_board_create_task",),
        ),
        FunctionTool(
            name="slack_fetch_channel_history",
            capability="slack.read.history",
            operation="fetch_history",
            domain="slack",
            schema=SLACK_FETCH_CHANNEL_HISTORY,
            run_fn=slack_fetch_channel_history,
            produces=("channel_text",),
        ),
    ]
