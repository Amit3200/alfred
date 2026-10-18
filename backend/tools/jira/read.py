"""JIRA read tools — get, search, list."""

from __future__ import annotations

from typing import Any

from backend.ai.base import ToolSchema
from backend.domains.jira.models import SearchIssuesRequest
from backend.domains.jira.service import JiraService
from backend.tools.base.tool import BaseTool, ToolContext
from backend.tools.jira.schemas import GET_JIRA_ISSUE, JIRA_SEARCH, LIST_JIRA_ISSUES
from backend.tools.result import ToolResult


def _service(ctx: ToolContext) -> JiraService:
    return JiraService.from_config(ctx.config)


class JiraGetIssueTool(BaseTool):
    name = "get_jira_issue"
    capability = "jira.read.single"
    operation = "read"
    domain = "jira"

    def schema(self) -> ToolSchema:
        return GET_JIRA_ISSUE

    def run(self, ctx: ToolContext, arguments: dict[str, Any]) -> ToolResult:
        key = str(arguments.get("issue_key") or "").strip()
        if not key:
            return ToolResult.error("issue_key is required.")
        try:
            detail = _service(ctx).get_issue(key)
            return ToolResult.jira_detail(detail)
        except (RuntimeError, ValueError) as exc:
            return ToolResult.error(str(exc))


class JiraSearchTool(BaseTool):
    name = "jira_search"
    capability = "jira.read.list"
    operation = "search"
    domain = "jira"

    def schema(self) -> ToolSchema:
        return JIRA_SEARCH

    def run(self, ctx: ToolContext, arguments: dict[str, Any]) -> ToolResult:
        req = SearchIssuesRequest.from_args(arguments)
        if not req.jql:
            return ToolResult.error("jql is required.")
        jql = req.jql
        live = ctx.get("current_task")
        if live is None:
            gov = getattr(ctx.get("registry"), "governance", None)
            live = getattr(gov, "task", None) if gov is not None else None
        if live is not None:
            from backend.routing.jira.context import scope_jql_for_task

            jql = scope_jql_for_task(jql, live, ctx.config)
        try:
            issues = _service(ctx).search_issues(
                SearchIssuesRequest(jql=jql, max_results=req.max_results)
            )
            return ToolResult.jira_list(issues)
        except (RuntimeError, ValueError) as exc:
            return ToolResult.error(str(exc))


class JiraListIssuesTool(BaseTool):
    name = "list_jira_issues"
    capability = "jira.read.list"
    operation = "list"
    domain = "jira"

    def schema(self) -> ToolSchema:
        return LIST_JIRA_ISSUES

    def run(self, ctx: ToolContext, arguments: dict[str, Any]) -> ToolResult:
        req = SearchIssuesRequest.from_args(arguments)
        try:
            issues = _service(ctx).search_issues(req)
            return ToolResult.jira_list(issues)
        except (RuntimeError, ValueError) as exc:
            return ToolResult.error(str(exc))
