"""Slack List board domain service — create/update/search/comment."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.db.slack_board_store import SlackBoardStore
from backend.domains.slack_board.formatting import (
    build_board_task_details,
    finalize_board_create_fields,
    normalize_board_severity,
)
from backend.domains.slack_board.models import (
    CommentTaskRequest,
    CreateTaskRequest,
    SearchTasksRequest,
    UpdateTaskRequest,
)
from backend.domains.slack_board.operations import (
    create_board_task,
    get_board_task,
    post_ticket_comment,
    resolve_board_for_task,
    search_board_tasks,
    update_board_task,
)
from backend.models.config import AlfredConfig
from backend.models.task import Task


class SlackBoardService:
    """Board verbs shared by tools and direct Slack handlers."""

    def __init__(
        self,
        *,
        config: AlfredConfig,
        client: Any,
        store: SlackBoardStore,
        data_dir: Path | None = None,
    ) -> None:
        self.config = config
        self.client = client
        self.store = store
        self.data_dir = data_dir

    @classmethod
    def from_config(
        cls,
        config: AlfredConfig,
        *,
        data_dir: Path | None,
        client: Any | None = None,
    ) -> SlackBoardService:
        token = (config.slack.bot_token or "").strip()
        if not token:
            raise RuntimeError("Slack bot token is not configured.")
        if client is None:
            from slack_sdk import WebClient

            client = WebClient(token=token)
        store = SlackBoardStore(data_dir or Path(".alfred"))
        return cls(config=config, client=client, store=store, data_dir=data_dir)

    def bot_user_id(self) -> str:
        try:
            auth = self.client.auth_test()
            return str(auth.get("user_id") or "")
        except Exception:
            return ""

    def resolve_board(self, task: Task | None) -> Any:
        if task is None:
            return None
        return resolve_board_for_task(self.config, task, data_dir=self.data_dir)

    def create_task(self, req: CreateTaskRequest, *, task: Task | None = None) -> dict[str, Any]:
        board = self.resolve_board(task)
        if board is None:
            raise RuntimeError("No Slack List board configured for this channel.")
        severity = normalize_board_severity(req.severity)
        assignee_user_id = req.assignee_user_id
        if task is not None:
            finalized = finalize_board_create_fields(
                severity=severity,
                assignee_user_id=assignee_user_id,
                requester_user_id=task.user_id or "",
                bot_user_id=self.bot_user_id(),
                default_assignee_to_requester=not bool(task.thread_ts),
            )
            severity = finalized["severity"]
            assignee_user_id = finalized["assignee_user_id"]
        description = req.description
        team_id = ""
        try:
            auth = self.client.auth_test()
            team_id = str(auth.get("team_id") or "")
        except Exception:
            pass
        if not description and task and task.channel_id and task.thread_ts:
            from backend.integrations.slack.context import fetch_thread_messages, messages_to_text

            try:
                messages = fetch_thread_messages(
                    self.client,
                    task,
                    limit=50,
                    bot_user_id=self.bot_user_id(),
                )
                messages_text = messages_to_text(messages) or ""
                description = build_board_task_details(
                    messages_text=messages_text,
                    channel_id=task.channel_id or "",
                    thread_ts=task.thread_ts or "",
                    team_id=team_id,
                    task_title=req.title,
                    bot_user_id=self.bot_user_id(),
                )
            except Exception as exc:
                description = f"Thread context unavailable: {exc}"
        if not description:
            description = build_board_task_details(
                channel_id=(task.channel_id if task else "") or req.channel_id,
                thread_ts=(task.thread_ts if task else "") or req.thread_ts,
                team_id=team_id,
                task_title=req.title,
            )
        return create_board_task(
            self.client,
            self.config,
            self.store,
            board,
            title=req.title,
            description=description,
            severity=severity,
            merchant=req.merchant,
            assignee_user_id=assignee_user_id or req.assignee_user_id,
            channel_id=(task.channel_id if task else "") or req.channel_id,
            thread_ts=(task.thread_ts if task else "") or req.thread_ts,
        )

    def update_task(self, req: UpdateTaskRequest) -> dict[str, Any]:
        return update_board_task(
            self.client,
            self.config,
            self.store,
            ticket_ref=req.ticket_ref,
            status=req.status,
            assignee_user_id=req.assignee_user_id,
            severity=normalize_board_severity(req.severity),
            channel_id=req.channel_id,
            record_id_hint=req.record_id_hint,
        )

    def search_tasks(self, req: SearchTasksRequest, *, task: Task | None = None) -> list[dict[str, Any]]:
        board = self.resolve_board(task)
        if board is None:
            raise RuntimeError("No Slack List board configured for this channel.")
        return search_board_tasks(
            self.client,
            self.config,
            self.store,
            board,
            query=req.query,
            status=req.status,
            limit=req.limit,
        )

    def get_task(self, ticket_ref: str) -> dict[str, Any]:
        return get_board_task(self.client, self.config, self.store, ticket_ref)

    def comment(self, req: CommentTaskRequest) -> dict[str, Any]:
        return post_ticket_comment(
            self.client,
            self.store,
            ticket_ref=req.ticket_ref,
            text=req.text,
            fallback_channel=req.channel_id,
            fallback_thread=req.thread_ts,
        )
