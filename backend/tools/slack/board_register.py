"""Slack List board write tools."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.db.slack_board_store import SlackBoardStore
from backend.integrations.slack.board_service import (
    board_enabled,
    create_board_task,
    get_board_task,
    post_ticket_comment,
    resolve_board_for_task,
    search_board_tasks,
    update_board_task,
)
from backend.models.config import AlfredConfig
from backend.models.task import Task
from backend.routing.slack_board_intent import (
    build_board_task_details,
    normalize_board_severity,
    references_thread_context,
)
from backend.tools.registry import ToolRegistry
from backend.tools.result import ToolResult
from backend.tools.slack.board_schemas import (
    SLACK_BOARD_COMMENT,
    SLACK_BOARD_CREATE_TASK,
    SLACK_BOARD_GET_TASK,
    SLACK_BOARD_SEARCH_TASKS,
    SLACK_BOARD_UPDATE_TASK,
)


def register_slack_board_tools(
    registry: ToolRegistry,
    config: AlfredConfig,
    *,
    data_dir: Path | None = None,
    default_task: Task | None = None,
) -> None:
    if not board_enabled(config, data_dir):
        return
    token = (config.slack.bot_token or "").strip()
    if not token:
        return

    from slack_sdk import WebClient

    client = WebClient(token=token)
    store = SlackBoardStore(data_dir or Path(".alfred"))
    task = default_task

    def _current(args: dict[str, Any]) -> Task | None:
        current = getattr(registry, "current_task", None) or task
        if current is not None:
            return current
        channel_id = str(args.get("channel_id") or "").strip()
        if not channel_id:
            return None
        return Task(
            source="slack",
            user_id="",
            channel_id=channel_id,
            thread_ts=str(args.get("thread_ts") or ""),
            raw_text="",
            cleaned_intent="",
        )

    def _board_or_error(current: Task | None) -> tuple[Any, ToolResult | None]:
        if current is None:
            return None, ToolResult.error("Slack board tools require channel context.")
        board = resolve_board_for_task(config, current, data_dir=data_dir)
        if board is None:
            return None, ToolResult.error("No Slack List board configured for this channel.")
        return board, None

    def create_handler(args: dict[str, Any]) -> ToolResult:
        current = _current(args)
        board, err = _board_or_error(current)
        if err:
            return err
        title = str(args.get("title") or "").strip()
        if not title:
            return ToolResult.error("title is required.")
        description = str(args.get("description") or "").strip()
        severity = normalize_board_severity(str(args.get("severity") or ""))
        team_id = ""
        try:
            auth = client.auth_test()
            team_id = str(auth.get("team_id") or "")
        except Exception:
            pass
        if not description and current and current.channel_id and current.thread_ts:
            from backend.integrations.slack.context import (
                fetch_thread_messages,
                messages_to_text,
            )

            try:
                messages = fetch_thread_messages(
                    client,
                    current,
                    limit=50,
                    bot_user_id=_bot_user_id(client),
                )
                messages_text = messages_to_text(messages) or ""
                description = build_board_task_details(
                    messages_text=messages_text,
                    channel_id=current.channel_id or "",
                    thread_ts=current.thread_ts or "",
                    team_id=team_id,
                    task_title=title,
                    bot_user_id=_bot_user_id(client),
                )
            except Exception as exc:
                description = f"Thread context unavailable: {exc}"
        if not description:
            description = build_board_task_details(
                channel_id=current.channel_id or "",
                thread_ts=current.thread_ts or "",
                team_id=team_id,
                task_title=title,
            )
        try:
            result = create_board_task(
                client,
                config,
                store,
                board,
                title=title,
                description=description,
                severity=severity,
                merchant=str(args.get("merchant") or ""),
                assignee_user_id=str(args.get("assignee_user_id") or ""),
                channel_id=current.channel_id or "",
                thread_ts=current.thread_ts or "",
            )
            return ToolResult(kind="slack_board_task", data=result)
        except Exception as exc:
            return ToolResult.error(str(exc))

    def update_handler(args: dict[str, Any]) -> ToolResult:
        current = _current(args)
        ticket_ref = str(args.get("ticket_ref") or "").strip()
        if not ticket_ref:
            return ToolResult.error("ticket_ref is required.")
        try:
            result = update_board_task(
                client,
                config,
                store,
                ticket_ref=ticket_ref,
                status=str(args.get("status") or ""),
                assignee_user_id=str(args.get("assignee_user_id") or ""),
                severity=normalize_board_severity(str(args.get("severity") or "")),
                channel_id=(current.channel_id if current else "") or "",
            )
            return ToolResult(kind="slack_board_task", data=result)
        except Exception as exc:
            return ToolResult.error(str(exc))

    def search_handler(args: dict[str, Any]) -> ToolResult:
        current = _current(args)
        board, err = _board_or_error(current)
        if err:
            return err
        try:
            rows = search_board_tasks(
                client,
                config,
                store,
                board,
                query=str(args.get("query") or ""),
                status=str(args.get("status") or ""),
                limit=int(args.get("limit") or 20),
            )
            return ToolResult(kind="slack_board_search", data={"results": rows, "count": len(rows)})
        except Exception as exc:
            return ToolResult.error(str(exc))

    def get_handler(args: dict[str, Any]) -> ToolResult:
        ticket_ref = str(args.get("ticket_ref") or "").strip()
        if not ticket_ref:
            return ToolResult.error("ticket_ref is required.")
        try:
            result = get_board_task(client, config, store, ticket_ref)
            return ToolResult(kind="slack_board_task", data=result)
        except Exception as exc:
            return ToolResult.error(str(exc))

    def comment_handler(args: dict[str, Any]) -> ToolResult:
        current = _current(args)
        ticket_ref = str(args.get("ticket_ref") or "").strip()
        text = str(args.get("text") or "").strip()
        if not ticket_ref or not text:
            return ToolResult.error("ticket_ref and text are required.")
        try:
            result = post_ticket_comment(
                client,
                store,
                ticket_ref=ticket_ref,
                text=text,
                fallback_channel=(current.channel_id if current else "") or "",
                fallback_thread=(current.thread_ts if current else "") or "",
            )
            return ToolResult(kind="slack_board_comment", data=result)
        except Exception as exc:
            return ToolResult.error(str(exc))

    registry.register(SLACK_BOARD_CREATE_TASK, create_handler)
    registry.register(SLACK_BOARD_UPDATE_TASK, update_handler)
    registry.register(SLACK_BOARD_SEARCH_TASKS, search_handler)
    registry.register(SLACK_BOARD_GET_TASK, get_handler)
    registry.register(SLACK_BOARD_COMMENT, comment_handler)


def _bot_user_id(client: Any) -> str:
    try:
        auth = client.auth_test()
        return str(auth.get("user_id") or "")
    except Exception:
        return ""
