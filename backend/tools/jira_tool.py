"""JIRA tools — list/get issues, transitions, comments, and Git links."""

from __future__ import annotations
from backend.integrations.identity.user_identity import build_workspace_identity_map
from backend.integrations.identity.user_identity import lookup_user_identity


from typing import Any

from backend.ai.base import ToolSchema
from backend.integrations.jira.api import JiraApiClient
from backend.models.config import AlfredConfig
from backend.tools.registry import ToolRegistry
from backend.tools.result import ToolResult

LIST_JIRA_ISSUES = ToolSchema(
    name="list_jira_issues",
    description=(
        "Search JIRA issues using JQL or filters (project, status, assignee). "
        "Use for open tickets, my tasks, or sprint work."
    ),
    parameters={
        "type": "object",
        "properties": {
            "jql": {
                "type": "string",
                "description": "Optional JQL query. Overrides project/status filters when set.",
            },
            "project": {
                "type": "string",
                "description": "Project key, e.g. ENG. Defaults to jira.default_project.",
            },
            "status": {
                "type": "string",
                "description": "Status name filter, e.g. 'In Progress'.",
            },
            "assignee": {
                "type": "string",
                "description": "Assignee username or email.",
            },
            "max_results": {
                "type": "integer",
                "description": "Max issues to return (default 25, max 100).",
            },
        },
        "required": [],
    },
)

GET_JIRA_ISSUE = ToolSchema(
    name="get_jira_issue",
    description="Get full details for a JIRA issue by key (e.g. ENG-123).",
    parameters={
        "type": "object",
        "properties": {
            "issue_key": {
                "type": "string",
                "description": "Issue key, e.g. ENG-123.",
            },
        },
        "required": ["issue_key"],
    },
)

TRANSITION_JIRA_ISSUE = ToolSchema(
    name="transition_jira_issue",
    description=(
        "Move a JIRA issue to a new status using a transition or target status name. "
        "Only use when the user explicitly asks to change ticket status."
    ),
    parameters={
        "type": "object",
        "properties": {
            "issue_key": {"type": "string", "description": "Issue key, e.g. ENG-123."},
            "transition": {
                "type": "string",
                "description": "Transition name or target status, e.g. 'In Review' or 'Done'.",
            },
        },
        "required": ["issue_key", "transition"],
    },
)

ADD_JIRA_COMMENT = ToolSchema(
    name="add_jira_comment",
    description="Add a comment to a JIRA issue. Only when the user explicitly asks.",
    parameters={
        "type": "object",
        "properties": {
            "issue_key": {"type": "string", "description": "Issue key, e.g. ENG-123."},
            "comment": {"type": "string", "description": "Comment text."},
        },
        "required": ["issue_key", "comment"],
    },
)

LINK_JIRA_ISSUE = ToolSchema(
    name="link_jira_issue",
    description=(
        "Attach a remote link (GitHub PR, branch URL, doc) to a JIRA issue. "
        "Use to connect tickets with pull requests."
    ),
    parameters={
        "type": "object",
        "properties": {
            "issue_key": {"type": "string", "description": "Issue key, e.g. ENG-123."},
            "url": {"type": "string", "description": "URL to link, e.g. GitHub PR."},
            "title": {
                "type": "string",
                "description": "Optional link title shown in JIRA.",
            },
        },
        "required": ["issue_key", "url"],
    },
)

JIRA_SEARCH = ToolSchema(
    name="jira_search",
    description="Search JIRA issues using JQL.",
    parameters={
        "type": "object",
        "properties": {
            "jql": {
                "type": "string",
                "description": "JQL query, e.g. assignee = currentUser() AND status != Done",
            },
            "max_results": {
                "type": "integer",
                "description": "Max issues to return (default 25, max 100).",
            },
        },
        "required": ["jql"],
    },
)

LOOKUP_USER_IDENTITY = ToolSchema(
    name="lookup_user_identity",
    description=(
        "Map a Slack user to JIRA identity fields (names, emails, handles). "
        "Use when the user asks for Slack/JIRA email, handle, or assignee map entries — "
        "not for listing tickets."
    ),
    parameters={
        "type": "object",
        "properties": {
            "slack_user_id": {
                "type": "string",
                "description": "Slack user ID from an @mention, e.g. U01234567.",
            },
            "query": {
                "type": "string",
                "description": "Display name or email to look up when no Slack ID is available.",
            },
        },
        "required": [],
    },
)

BUILD_WORKSPACE_IDENTITY_MAP = ToolSchema(
    name="build_workspace_identity_map",
    description=(
        "Build a Slack workspace-wide identity map: list all human Slack members and match "
        "each to JIRA and GitHub (email/name/handle). Use for 'all users' / assignee map requests."
    ),
    parameters={
        "type": "object",
        "properties": {
            "include_github": {
                "type": "boolean",
                "description": "When true (default), match GitHub org members from git.default_org.",
            },
        },
        "required": [],
    },
)

JIRA_UPDATE_ISSUE = ToolSchema(
    name="jira_update_issue",
    description=(
        "Update a JIRA issue summary and/or description. "
        "Appends to description by default unless replace_description is true."
    ),
    parameters={
        "type": "object",
        "properties": {
            "issue_key": {"type": "string", "description": "Issue key, e.g. PROJ-123."},
            "summary": {"type": "string", "description": "New summary/title."},
            "description": {"type": "string", "description": "Description text to add or replace."},
            "replace_description": {
                "type": "boolean",
                "description": "If true, replace description instead of appending (default false).",
            },
        },
        "required": ["issue_key"],
    },
)

JIRA_ADD_COMMENT = ToolSchema(
    name="jira_add_comment",
    description="Add a comment to a JIRA issue.",
    parameters={
        "type": "object",
        "properties": {
            "issue_key": {"type": "string", "description": "Issue key, e.g. PROJ-123."},
            "comment": {"type": "string", "description": "Comment text."},
        },
        "required": ["issue_key", "comment"],
    },
)

JIRA_CREATE_ISSUE = ToolSchema(
    name="jira_create_issue",
    description="Create a new JIRA issue (Task, Story, Epic, Bug, etc.).",
    parameters={
        "type": "object",
        "properties": {
            "project": {"type": "string", "description": "Project key, e.g. ENG."},
            "summary": {"type": "string", "description": "Issue title."},
            "issue_type": {
                "type": "string",
                "description": "Issue type name, e.g. Task, Story, Epic, Bug.",
            },
            "priority": {"type": "string", "description": "Optional priority, e.g. High."},
            "description": {"type": "string", "description": "Optional description."},
        },
        "required": ["project", "summary", "issue_type"],
    },
)


def register_jira_tools(registry: ToolRegistry, config: AlfredConfig) -> None:
    def workspace_identity_handler(args: dict[str, Any]) -> ToolResult:
        pass

        data = build_workspace_identity_map(
            config,
            include_github=bool(args.get("include_github", True)),
        )
        if data.get("error"):
            return ToolResult.error(str(data["error"]))
        return ToolResult(kind="user_identity", data=data)

    def identity_handler(args: dict[str, Any]) -> ToolResult:
        pass

        data = lookup_user_identity(
            config,
            slack_user_id=str(args.get("slack_user_id") or ""),
            query=str(args.get("query") or ""),
            targets=args.get("targets"),
        )
        if data.get("error"):
            return ToolResult.error(str(data["error"]))
        return ToolResult(kind="user_identity", data=data)

    if not config.jira.enabled and not config.slack.enabled:
        return

    registry.register(BUILD_WORKSPACE_IDENTITY_MAP, workspace_identity_handler)
    registry.register(LOOKUP_USER_IDENTITY, identity_handler)

    if not config.jira.enabled:
        return

    try:
        client = JiraApiClient.from_alfred_config(config)
    except RuntimeError:
        return

    def list_handler(args: dict[str, Any]) -> ToolResult:
        try:
            issues = client.search_issues(
                jql=str(args.get("jql") or "") or None,
                project=str(args.get("project") or "") or None,
                status=str(args.get("status") or "") or None,
                assignee=str(args.get("assignee") or "") or None,
                max_results=int(args.get("max_results") or 25),
            )
            return ToolResult.jira_list(issues)
        except (RuntimeError, ValueError) as exc:
            return ToolResult.error(str(exc))

    def get_handler(args: dict[str, Any]) -> ToolResult:
        key = str(args.get("issue_key") or "").strip()
        if not key:
            return ToolResult.error("issue_key is required.")
        try:
            detail = client.get_issue(key)
            return ToolResult.jira_detail(detail)
        except (RuntimeError, ValueError) as exc:
            return ToolResult.error(str(exc))

    def transition_handler(args: dict[str, Any]) -> ToolResult:
        key = str(args.get("issue_key") or "").strip()
        transition = str(args.get("transition") or "").strip()
        if not key or not transition:
            return ToolResult.error("issue_key and transition are required.")
        try:
            result = client.transition_issue(key, transition=transition)
            return ToolResult.jira_action("transition", result)
        except (RuntimeError, ValueError) as exc:
            return ToolResult.error(str(exc))

    def comment_handler(args: dict[str, Any]) -> ToolResult:
        key = str(args.get("issue_key") or "").strip()
        comment = str(args.get("comment") or "").strip()
        if not key or not comment:
            return ToolResult.error("issue_key and comment are required.")
        try:
            result = client.add_comment(key, comment)
            return ToolResult.jira_action("comment", result)
        except (RuntimeError, ValueError) as exc:
            return ToolResult.error(str(exc))

    def link_handler(args: dict[str, Any]) -> ToolResult:
        key = str(args.get("issue_key") or "").strip()
        url = str(args.get("url") or "").strip()
        if not key or not url:
            return ToolResult.error("issue_key and url are required.")
        try:
            result = client.link_remote(
                key,
                url=url,
                title=str(args.get("title") or "") or None,
            )
            return ToolResult.jira_action("link", result)
        except (RuntimeError, ValueError) as exc:
            return ToolResult.error(str(exc))

    def search_handler(args: dict[str, Any]) -> ToolResult:
        jql = str(args.get("jql") or "").strip()
        if not jql:
            return ToolResult.error("jql is required.")
        try:
            issues = client.search_issues(
                jql=jql,
                max_results=int(args.get("max_results") or 25),
            )
            return ToolResult.jira_list(issues)
        except (RuntimeError, ValueError) as exc:
            return ToolResult.error(str(exc))

    def update_handler(args: dict[str, Any]) -> ToolResult:
        key = str(args.get("issue_key") or "").strip()
        if not key:
            return ToolResult.error("issue_key is required.")
        summary = str(args.get("summary") or "") or None
        description = args.get("description")
        desc_text = str(description).strip() if description is not None else None
        replace = bool(args.get("replace_description"))
        if summary is None and desc_text is None:
            return ToolResult.error("At least one of summary or description is required.")
        try:
            result = client.update_issue(
                key,
                summary=summary,
                description=desc_text,
                append_description=not replace,
            )
            return ToolResult.jira_action("update", result)
        except (RuntimeError, ValueError) as exc:
            return ToolResult.error(str(exc))

    def jira_comment_handler(args: dict[str, Any]) -> ToolResult:
        return comment_handler(args)

    def create_handler(args: dict[str, Any]) -> ToolResult:
        project = str(args.get("project") or "").strip()
        summary = str(args.get("summary") or "").strip()
        issue_type = str(args.get("issue_type") or "").strip()
        if not project or not summary or not issue_type:
            return ToolResult.error("project, summary, and issue_type are required.")
        try:
            result = client.create_issue(
                project=project,
                summary=summary,
                issue_type=issue_type,
                priority=str(args.get("priority") or "") or None,
                description=str(args.get("description") or "") or None,
            )
            return ToolResult.jira_action("create", result)
        except (RuntimeError, ValueError) as exc:
            return ToolResult.error(str(exc))

    registry.register(LIST_JIRA_ISSUES, list_handler)
    registry.register(GET_JIRA_ISSUE, get_handler)
    registry.register(TRANSITION_JIRA_ISSUE, transition_handler)
    registry.register(ADD_JIRA_COMMENT, comment_handler)
    registry.register(LINK_JIRA_ISSUE, link_handler)
    registry.register(JIRA_SEARCH, search_handler)
    registry.register(JIRA_UPDATE_ISSUE, update_handler)
    registry.register(JIRA_ADD_COMMENT, jira_comment_handler)
    registry.register(JIRA_CREATE_ISSUE, create_handler)
