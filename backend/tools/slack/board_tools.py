"""Slack List board tools — class-based operations."""

from __future__ import annotations

from typing import Any

from backend.ai.base import ToolSchema
from backend.domains.slack_board.models import (
    CommentTaskRequest,
    CreateTaskRequest,
    SearchTasksRequest,
    UpdateTaskRequest,
)
from backend.domains.slack_board.service import SlackBoardService
from backend.models.task import Task
from backend.tools.base.bundle import ToolBundle
from backend.tools.base.tool import BaseTool, ToolContext
from backend.tools.result import ToolResult
from backend.tools.slack.board_schemas import (
    SLACK_BOARD_COMMENT,
    SLACK_BOARD_CREATE_TASK,
    SLACK_BOARD_GET_TASK,
    SLACK_BOARD_SEARCH_TASKS,
    SLACK_BOARD_UPDATE_TASK,
)


def _task(ctx: ToolContext, arguments: dict[str, Any]) -> Task | None:
    live = ctx.get("current_task") or ctx.get("default_task")
    if live is not None:
        return live
    channel_id = str(arguments.get("channel_id") or ctx.channel_id or "").strip()
    if not channel_id:
        return None
    return Task(
        source="slack",
        user_id=ctx.user_id or "",
        channel_id=channel_id,
        thread_ts=str(arguments.get("thread_ts") or ctx.thread_ts or ""),
        raw_text="",
        cleaned_intent="",
    )


def _service(ctx: ToolContext) -> SlackBoardService:
    return SlackBoardService.from_config(ctx.config, data_dir=ctx.data_dir)


class SlackBoardCreateTaskTool(BaseTool):
    name = "slack_board_create_task"
    capability = "slack.board.write.create"
    operation = "create"
    domain = "slack_board"
    consumes = ("title",)
    produces = ("ticket_ref",)
    next_tools = ("slack_board_update_task", "slack_board_comment")

    def schema(self) -> ToolSchema:
        return SLACK_BOARD_CREATE_TASK

    def run(self, ctx: ToolContext, arguments: dict[str, Any]) -> ToolResult:
        task = _task(ctx, arguments)
        req = CreateTaskRequest.from_args(
            arguments,
            channel_id=(task.channel_id if task else "") or "",
            thread_ts=(task.thread_ts if task else "") or "",
        )
        error = req.validate()
        if error:
            return ToolResult.error(error)
        if task is None:
            return ToolResult.error("Slack board tools require channel context.")
        try:
            result = _service(ctx).create_task(req, task=task)
            return ToolResult(kind="slack_board_task", data=result)
        except Exception as exc:
            return ToolResult.error(str(exc))


class SlackBoardUpdateTaskTool(BaseTool):
    name = "slack_board_update_task"
    capability = "slack.board.write.update"
    operation = "update"
    domain = "slack_board"

    def schema(self) -> ToolSchema:
        return SLACK_BOARD_UPDATE_TASK

    def run(self, ctx: ToolContext, arguments: dict[str, Any]) -> ToolResult:
        task = _task(ctx, arguments)
        req = UpdateTaskRequest.from_args(
            arguments,
            channel_id=(task.channel_id if task else "") or "",
        )
        error = req.validate()
        if error:
            return ToolResult.error(error)
        try:
            result = _service(ctx).update_task(req)
            return ToolResult(kind="slack_board_task", data=result)
        except Exception as exc:
            return ToolResult.error(str(exc))


class SlackBoardSearchTasksTool(BaseTool):
    name = "slack_board_search_tasks"
    capability = "slack.board.read.search"
    operation = "search"
    domain = "slack_board"

    def schema(self) -> ToolSchema:
        return SLACK_BOARD_SEARCH_TASKS

    def run(self, ctx: ToolContext, arguments: dict[str, Any]) -> ToolResult:
        task = _task(ctx, arguments)
        if task is None:
            return ToolResult.error("Slack board tools require channel context.")
        req = SearchTasksRequest.from_args(arguments)
        try:
            rows = _service(ctx).search_tasks(req, task=task)
            return ToolResult(kind="slack_board_search", data={"results": rows, "count": len(rows)})
        except Exception as exc:
            return ToolResult.error(str(exc))


class SlackBoardGetTaskTool(BaseTool):
    name = "slack_board_get_task"
    capability = "slack.board.read.single"
    operation = "read"
    domain = "slack_board"

    def schema(self) -> ToolSchema:
        return SLACK_BOARD_GET_TASK

    def run(self, ctx: ToolContext, arguments: dict[str, Any]) -> ToolResult:
        ticket_ref = str(arguments.get("ticket_ref") or "").strip()
        if not ticket_ref:
            return ToolResult.error("ticket_ref is required.")
        try:
            result = _service(ctx).get_task(ticket_ref)
            return ToolResult(kind="slack_board_task", data=result)
        except Exception as exc:
            return ToolResult.error(str(exc))


class SlackBoardCommentTool(BaseTool):
    name = "slack_board_comment"
    capability = "slack.board.write.comment"
    operation = "comment"
    domain = "slack_board"

    def schema(self) -> ToolSchema:
        return SLACK_BOARD_COMMENT

    def run(self, ctx: ToolContext, arguments: dict[str, Any]) -> ToolResult:
        task = _task(ctx, arguments)
        req = CommentTaskRequest.from_args(
            arguments,
            channel_id=(task.channel_id if task else "") or "",
            thread_ts=(task.thread_ts if task else "") or "",
        )
        error = req.validate()
        if error:
            return ToolResult.error(error)
        try:
            result = _service(ctx).comment(req)
            return ToolResult(kind="slack_board_comment", data=result)
        except Exception as exc:
            return ToolResult.error(str(exc))


class SlackBoardToolBundle(ToolBundle):
    capability_prefix = "slack.board"

    def tools(self) -> list[BaseTool]:
        return [
            SlackBoardCreateTaskTool(),
            SlackBoardUpdateTaskTool(),
            SlackBoardSearchTasksTool(),
            SlackBoardGetTaskTool(),
            SlackBoardCommentTool(),
        ]
