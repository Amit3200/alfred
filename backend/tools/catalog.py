"""Tool names grouped by integration — used for lazy registration."""

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

GOOGLE_TOOLS = frozenset(
    {
        "google_read_sheet",
        "google_write_sheet",
        "google_append_sheet",
        "google_read_doc",
        "google_create_doc",
        "google_append_doc",
    }
)

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
    | JIRA_MODULE_TOOLS
    | AWS_TOOLS
    | GOOGLE_TOOLS
    | WEB_TOOLS
    | COMPANY_SCRIPT_TOOLS
    | SCHEDULE_TOOLS
)
