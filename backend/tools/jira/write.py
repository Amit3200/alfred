"""JIRA write tools — create, assign, transition, comment, update, link."""

from __future__ import annotations

from typing import Any

from backend.ai.base import ToolSchema
from backend.domains.jira.models import (
    AssignIssueRequest,
    CommentRequest,
    CreateIssueRequest,
    LinkIssueRequest,
    TransitionRequest,
    UpdateIssueRequest,
)
from backend.domains.jira.service import JiraService
from backend.tools.base.tool import BaseTool, ToolContext
from backend.tools.jira.schemas import (
    ADD_JIRA_COMMENT,
    JIRA_ADD_COMMENT,
    JIRA_ASSIGN_ISSUE,
    JIRA_CREATE_ISSUE,
    JIRA_UPDATE_ISSUE,
    LINK_JIRA_ISSUE,
    TRANSITION_JIRA_ISSUE,
)
from backend.tools.result import ToolResult


def _service(ctx: ToolContext) -> JiraService:
    return JiraService.from_config(ctx.config)


def _enriched_description(ctx: ToolContext, args: dict[str, Any]) -> str:
    from backend.domains.jira.description import enrich_jira_create_description

    registry = ctx.get("registry")
    session_metadata = getattr(registry, "session_metadata", None) if registry is not None else None
    if not isinstance(session_metadata, dict):
        session_metadata = {}
    task = ctx.get("current_task")
    return enrich_jira_create_description(
        str(args.get("description") or ""),
        summary=str(args.get("summary") or ""),
        task=task,
        session_metadata=session_metadata,
        channel_id=str(ctx.channel_id or ""),
        thread_ts=str(ctx.thread_ts or ""),
    )


def _resolve_create_project(ctx: ToolContext, args: dict[str, Any]) -> str:
    from backend.routing.jira.context import _project_from_channel
    from backend.routing.jira.project_key import normalize_jira_project_key

    channel_key = _project_from_channel(
        str(ctx.channel_id or ""),
        ctx.config,
        data_dir=ctx.data_dir,
    )
    if channel_key:
        return channel_key
    raw = str(args.get("project") or "").strip()
    if raw:
        return normalize_jira_project_key(raw, ctx.config.jira)
    return (ctx.config.jira.default_project or "").strip()


def _fallback_slack_board(ctx: ToolContext, args: dict[str, Any], exc: Exception) -> ToolResult | None:
    task = ctx.get("current_task")
    if task is None or ctx.data_dir is None or not (ctx.config.slack.bot_token or "").strip():
        return None
    from backend.domains.slack_board.operations import board_enabled, resolve_board_for_task

    if not board_enabled(ctx.config, ctx.data_dir):
        return None
    if resolve_board_for_task(ctx.config, task, data_dir=ctx.data_dir) is None:
        return None
    from slack_sdk import WebClient

    from backend.routing.slack_board.bootstrap import bootstrap_slack_board_create

    title = str(args.get("summary") or "").strip()
    note = bootstrap_slack_board_create(
        WebClient(token=ctx.config.slack.bot_token),
        ctx.config,
        task=task,
        data_dir=ctx.data_dir,
        title_override=title,
    )
    if "already created" not in (note or "").lower():
        return None
    return ToolResult(
        kind="jira_action",
        data={
            "action": "create_fallback_slack_board",
            "jira_error": str(exc),
            "message": (
                f"JIRA create failed ({exc}). Created the task on this channel's Slack List instead.\n\n{note}"
            ),
        },
    )


class JiraCreateIssueTool(BaseTool):
    name = "jira_create_issue"
    capability = "jira.write.create"
    operation = "create"
    domain = "jira"
    produces = ("issue_key",)
    next_tools = ("jira_assign_issue", "jira_add_comment")

    def schema(self) -> ToolSchema:
        return JIRA_CREATE_ISSUE

    def run(self, ctx: ToolContext, arguments: dict[str, Any]) -> ToolResult:
        from backend.domains.jira.thread_fields import (
            fetch_slack_thread_text,
            fill_jira_create_args,
            is_weak_jira_summary,
        )

        args = dict(arguments)
        task = ctx.get("current_task")
        request_text = ""
        session_title = ""
        if task is not None:
            request_text = (task.cleaned_intent or task.raw_text or "").strip()
        registry = ctx.get("registry")
        session_metadata = getattr(registry, "session_metadata", None) if registry is not None else None
        if isinstance(session_metadata, dict):
            session_title = str(dict(session_metadata.get("last_board_task") or {}).get("title") or "")
        args = fill_jira_create_args(
            args,
            request_text=request_text,
            thread_text=fetch_slack_thread_text(ctx, task),
            session_title=session_title,
        )
        args["project"] = _resolve_create_project(ctx, args)
        if not str(args.get("issue_type") or "").strip():
            args["issue_type"] = "Task"
        if is_weak_jira_summary(str(args.get("summary") or "")):
            return ToolResult.error(
                "Cannot create a JIRA issue without a real summary. "
                "Use the problem from this thread — never placeholders like "
                "`<to be provided by user>`."
            )
        args["description"] = _enriched_description(ctx, args)
        req = CreateIssueRequest.from_args(args)
        error = req.validate()
        if error:
            return ToolResult.error(error)
        try:
            result = _service(ctx).create_issue(req)
            return ToolResult.jira_action("create", result)
        except (RuntimeError, ValueError) as exc:
            fallback = _fallback_slack_board(ctx, args, exc)
            if fallback is not None:
                return fallback
            return ToolResult.error(str(exc))


class JiraAssignIssueTool(BaseTool):
    name = "jira_assign_issue"
    capability = "jira.write.assign"
    operation = "assign"
    domain = "jira"
    consumes = ("issue_key",)

    def schema(self) -> ToolSchema:
        return JIRA_ASSIGN_ISSUE

    def run(self, ctx: ToolContext, arguments: dict[str, Any]) -> ToolResult:
        req = AssignIssueRequest.from_args(arguments)
        error = req.validate()
        if error:
            return ToolResult.error(error)
        try:
            result = _service(ctx).assign_issue(req)
            return ToolResult.jira_action("assign", result)
        except (RuntimeError, ValueError) as exc:
            return ToolResult.error(str(exc))


class JiraTransitionIssueTool(BaseTool):
    name = "transition_jira_issue"
    capability = "jira.write.transition"
    operation = "transition"
    domain = "jira"

    def schema(self) -> ToolSchema:
        return TRANSITION_JIRA_ISSUE

    def run(self, ctx: ToolContext, arguments: dict[str, Any]) -> ToolResult:
        req = TransitionRequest.from_args(arguments)
        error = req.validate()
        if error:
            return ToolResult.error(error)
        try:
            result = _service(ctx).transition_issue(req)
            return ToolResult.jira_action("transition", result)
        except (RuntimeError, ValueError) as exc:
            return ToolResult.error(str(exc))


class JiraAddCommentTool(BaseTool):
    name = "jira_add_comment"
    capability = "jira.write.comment"
    operation = "comment"
    domain = "jira"

    def schema(self) -> ToolSchema:
        return JIRA_ADD_COMMENT

    def run(self, ctx: ToolContext, arguments: dict[str, Any]) -> ToolResult:
        req = CommentRequest.from_args(arguments)
        error = req.validate()
        if error:
            return ToolResult.error(error)
        try:
            result = _service(ctx).add_comment(req)
            return ToolResult.jira_action("comment", result)
        except (RuntimeError, ValueError) as exc:
            return ToolResult.error(str(exc))


class JiraAddCommentAliasTool(JiraAddCommentTool):
    """Legacy alias — same operation as jira_add_comment."""

    name = "add_jira_comment"
    capability = "jira.write.comment"

    def schema(self) -> ToolSchema:
        return ADD_JIRA_COMMENT


class JiraUpdateIssueTool(BaseTool):
    name = "jira_update_issue"
    capability = "jira.write.update"
    operation = "update"
    domain = "jira"

    def schema(self) -> ToolSchema:
        return JIRA_UPDATE_ISSUE

    def run(self, ctx: ToolContext, arguments: dict[str, Any]) -> ToolResult:
        from backend.domains.jira.thread_fields import fetch_slack_thread_text, fill_jira_update_args
        from backend.routing.entity_extractor import extract_entities

        args = dict(arguments)
        task = ctx.get("current_task")
        request_text = ""
        if task is not None:
            request_text = (task.cleaned_intent or task.raw_text or "").strip()
        thread_text = fetch_slack_thread_text(ctx, task)
        args = fill_jira_update_args(args, request_text=request_text, thread_text=thread_text)
        issue_key = str(args.get("issue_key") or "").strip()
        bag = extract_entities(issue_key, request_text, thread_text)
        if bag.issue_keys:
            args["issue_key"] = bag.issue_keys[0]
        req = UpdateIssueRequest.from_args(args)
        error = req.validate()
        if error:
            return ToolResult.error(error)
        try:
            result = _service(ctx).update_issue(req)
            return ToolResult.jira_action("update", result)
        except (RuntimeError, ValueError) as exc:
            return ToolResult.error(str(exc))


class JiraLinkIssueTool(BaseTool):
    name = "link_jira_issue"
    capability = "jira.write.link"
    operation = "link"
    domain = "jira"

    def schema(self) -> ToolSchema:
        return LINK_JIRA_ISSUE

    def run(self, ctx: ToolContext, arguments: dict[str, Any]) -> ToolResult:
        req = LinkIssueRequest.from_args(arguments)
        error = req.validate()
        if error:
            return ToolResult.error(error)
        try:
            result = _service(ctx).link_remote(req)
            return ToolResult.jira_action("link", result)
        except (RuntimeError, ValueError) as exc:
            return ToolResult.error(str(exc))
