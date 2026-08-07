"""Tool names grouped by integration — single source of truth for registration and observability."""

from __future__ import annotations

GIT_API_TOOLS = frozenset(
    {
        "list_my_prs",
        "list_prs",
        "get_pr",
        "get_pr_changes",
        "list_repos",
    }
)

GIT_LOCAL_TOOLS = frozenset(
    {
        "grep_repo",
        "read_file",
        "git_log",
        "git_blame",
        "git_show",
    }
)

GIT_WRITE_TOOLS = frozenset(
    {
        "git_prepare_branch",
        "write_file",
        "write_debug_script",
        "run_debug_script",
        "git_commit",
        "git_push_branch",
        "create_pull_request",
    }
)

GRAPHIFY_TOOLS = frozenset({"query_graph"})

REPO_DOC_TOOLS = frozenset(
    {
        "search_repo_docs",
        "read_repo_doc",
        "list_repo_docs",
    }
)

GIT_TOOLS = GIT_API_TOOLS | GIT_LOCAL_TOOLS | GIT_WRITE_TOOLS | GRAPHIFY_TOOLS

IDENTITY_TOOLS = frozenset(
    {
        "lookup_user_identity",
        "build_workspace_identity_map",
    }
)

JIRA_TOOLS = frozenset(
    {
        "list_jira_issues",
        "get_jira_issue",
        "transition_jira_issue",
        "add_jira_comment",
        "link_jira_issue",
        "jira_search",
        "jira_update_issue",
        "jira_add_comment",
        "jira_create_issue",
        "jira_assign_issue",
    }
)

JIRA_MODULE_TOOLS = JIRA_TOOLS | IDENTITY_TOOLS

AWS_TOOLS = frozenset(
    {
        "athena_query",
        "cloudwatch_query",
        "list_cloudwatch_log_groups",
    }
)

GOOGLE_SHEET_TOOLS = frozenset(
    {
        "google_create_sheet",
        "google_read_sheet",
        "google_write_sheet",
        "google_append_sheet",
    }
)

GOOGLE_DOC_TOOLS = frozenset(
    {
        "google_read_doc",
        "google_create_doc",
        "google_append_doc",
    }
)

GOOGLE_TOOLS = GOOGLE_SHEET_TOOLS | GOOGLE_DOC_TOOLS

SLACK_READ_TOOLS = frozenset(
    {
        "slack_fetch_thread",
        "slack_fetch_channel_history",
    }
)

SLACK_BOARD_TOOLS = frozenset(
    {
        "slack_board_create_task",
        "slack_board_update_task",
        "slack_board_search_tasks",
        "slack_board_get_task",
        "slack_board_comment",
    }
)

SLACK_TOOLS = SLACK_READ_TOOLS | SLACK_BOARD_TOOLS

WEB_TOOLS = frozenset({"web_search"})

COMPANY_SCRIPT_TOOLS = frozenset(
    {
        "list_company_scripts",
        "read_company_script_file",
        "write_company_script_file",
        "create_company_script_package",
        "run_company_script",
    }
)

SCHEDULE_TOOLS = frozenset(
    {
        "create_schedule",
        "list_schedules",
        "toggle_schedule",
        "delete_schedule",
        "update_schedule",
    }
)

ALL_KNOWN_TOOLS = (
    GIT_TOOLS
    | REPO_DOC_TOOLS
    | JIRA_MODULE_TOOLS
    | AWS_TOOLS
    | GOOGLE_TOOLS
    | SLACK_TOOLS
    | WEB_TOOLS
    | COMPANY_SCRIPT_TOOLS
    | SCHEDULE_TOOLS
)

# Per-tool domain for logging and observability (finer than category).
TOOL_DOMAINS: dict[str, str] = {
    **{name: "git" for name in GIT_API_TOOLS | GIT_LOCAL_TOOLS | GIT_WRITE_TOOLS | GRAPHIFY_TOOLS},
    **{name: "repo_docs" for name in REPO_DOC_TOOLS},
    **{name: "jira" for name in JIRA_TOOLS},
    **{name: "identity" for name in IDENTITY_TOOLS},
    **{name: "aws" for name in AWS_TOOLS},
    **{name: "google_sheet" for name in GOOGLE_SHEET_TOOLS},
    **{name: "google_doc" for name in GOOGLE_DOC_TOOLS},
    **{name: "slack" for name in SLACK_READ_TOOLS},
    **{name: "slack_write" for name in SLACK_BOARD_TOOLS},
    **{name: "web" for name in WEB_TOOLS},
    **{name: "script" for name in COMPANY_SCRIPT_TOOLS},
    **{name: "schedule" for name in SCHEDULE_TOOLS},
}


def tool_domain(tool_name: str) -> str:
    return TOOL_DOMAINS.get(tool_name, "other")


def tool_category(tool_name: str) -> str:
    """Coarser grouping for observability dashboards."""
    domain = tool_domain(tool_name)
    if domain.startswith("google_"):
        return "google"
    if domain == "identity":
        return "jira"
    return domain
