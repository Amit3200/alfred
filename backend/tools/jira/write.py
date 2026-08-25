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
        args = dict(arguments)
        if not str(args.get("project") or "").strip():
            args["project"] = (ctx.config.jira.default_project or "").strip()
        if not str(args.get("issue_type") or "").strip():
            args["issue_type"] = "Task"
        args["description"] = _enriched_description(ctx, args)
        req = CreateIssueRequest.from_args(args)
        error = req.validate()
        if error:
            return ToolResult.error(error)
        try:
            result = _service(ctx).create_issue(req)
            return ToolResult.jira_action("create", result)
        except (RuntimeError, ValueError) as exc:
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
        req = UpdateIssueRequest.from_args(arguments)
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
