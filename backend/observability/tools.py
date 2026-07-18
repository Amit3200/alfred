"""Tool name → category mapping for observability."""

from __future__ import annotations

GIT_TOOLS = frozenset(
    {
        "list_my_prs",
        "list_prs",
        "get_pr",
        "get_pr_changes",
        "list_repos",
        "grep_repo",
        "read_file",
        "git_log",
        "git_blame",
        "git_show",
        "query_graph",
    }
)

AWS_TOOLS = frozenset(
    {
        "athena_query",
        "cloudwatch_query",
        "list_cloudwatch_log_groups",
    }
)
SLACK_TOOLS = frozenset()
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
UI_TOOLS = frozenset()


WEB_TOOLS = frozenset({"web_search"})


def tool_category(tool_name: str) -> str:
    if tool_name in GIT_TOOLS:
        return "git"
    if tool_name in WEB_TOOLS:
        return "web"
    if tool_name in SLACK_TOOLS:
        return "slack"
    if tool_name in JIRA_TOOLS:
        return "jira"
    if tool_name in AWS_TOOLS:
        return "aws"
    if tool_name in UI_TOOLS:
        return "ui"
    return "other"
