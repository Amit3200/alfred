"""JIRA ToolSchema constants — MCP-compatible argument shapes."""

from __future__ import annotations

from backend.ai.base import ToolSchema

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

JIRA_CREATE_ISSUE = ToolSchema(
    name="jira_create_issue",
    description=(
        "Create a new JIRA issue (Task, Story, Epic, Bug, etc.). "
        "Always pass description: what was asked, relevant thread/Slack List context, "
        "and the Slack thread URL."
    ),
    parameters={
        "type": "object",
        "properties": {
            "project": {"type": "string", "description": "Project key, e.g. ENG."},
            "summary": {
                "type": "string",
                "description": (
                    "Issue title from the user's problem, not a placeholder. "
                    "Never use `<to be provided by user>`."
                ),
            },
            "issue_type": {
                "type": "string",
                "description": (
                    "Issue type name, e.g. Task, Story, Epic, Bug. "
                    "Default Task when omitted or unsure — never Ticket or Issue."
                ),
            },
            "priority": {"type": "string", "description": "Optional priority, e.g. High."},
            "description": {
                "type": "string",
                "description": (
                    "Required in practice. Summarize the request and thread. "
                    "Include the Slack thread permalink and Slack List id (e.g. TS-23) when known. "
                    "Never use `<to be provided by user>` or `<optional details from user>`."
                ),
            },
            "reporter": {
                "type": "string",
                "description": "Optional reporter name or email. Falls back to API token user if unknown.",
            },
            "assignee": {
                "type": "string",
                "description": "Optional assignee name or email. Omitted if user not found in JIRA.",
            },
        },
        "required": ["project", "summary", "issue_type"],
    },
)

JIRA_ASSIGN_ISSUE = ToolSchema(
    name="jira_assign_issue",
    description=(
        "Assign or reassign an EXISTING JIRA issue to a user by name, email, or account ID. "
        "Use when the user asks to assign a ticket that already exists."
    ),
    parameters={
        "type": "object",
        "properties": {
            "issue_key": {"type": "string", "description": "Issue key, e.g. PROJ-123."},
            "assignee": {
                "type": "string",
                "description": "Assignee display name, email, Slack-resolved email, or JIRA account ID.",
            },
        },
        "required": ["issue_key", "assignee"],
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

ADD_JIRA_COMMENT = ToolSchema(
    name="add_jira_comment",
    description="Add a comment to a JIRA issue. Only when the user explicitly asks. Legacy alias of jira_add_comment.",
    parameters=JIRA_ADD_COMMENT.parameters,
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
            "issue_key": {
                "type": "string",
                "description": "Issue key, e.g. PROJ-123. TECH 363 means TECH-363.",
            },
            "summary": {
                "type": "string",
                "description": "New summary/title from the user's details, never a placeholder.",
            },
            "description": {
                "type": "string",
                "description": (
                    "Description text to add or replace. Use the user's pasted details. "
                    "Never `<optional details from user>`."
                ),
            },
            "replace_description": {
                "type": "boolean",
                "description": "If true, replace description instead of appending (default false).",
            },
        },
        "required": ["issue_key"],
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
