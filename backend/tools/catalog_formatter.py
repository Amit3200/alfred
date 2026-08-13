"""Format tool catalog for LLM tool planner prompts."""

from __future__ import annotations

from backend.tools.catalog import (
    SLACK_BOARD_READ_TOOLS,
    SLACK_BOARD_WRITE_TOOLS,
    AWS_TOOLS,
    COMPANY_SCRIPT_TOOLS,
    GIT_TOOLS,
    GOOGLE_DOC_TOOLS,
    GOOGLE_SHEET_TOOLS,
    JIRA_TOOLS,
    REPO_DOC_TOOLS,
    SLACK_TOOLS,
    WEB_TOOLS,
    tool_domain,
)

# Short descriptions for planner — one line each.
_TOOL_DESCRIPTIONS: dict[str, str] = {
    "get_jira_issue": "Fetch one JIRA issue by key",
    "jira_search": "Search/list JIRA issues via JQL",
    "jira_create_issue": "Create a new JIRA issue",
    "jira_assign_issue": "Assign/reassign an existing JIRA issue",
    "jira_update_issue": "Update JIRA summary/description",
    "transition_jira_issue": "Change JIRA status within project workflow",
    "jira_add_comment": "Add comment to JIRA issue",
    "link_jira_issue": "Attach remote link (PR URL) to JIRA issue",
    "google_create_sheet": "CREATE new spreadsheet (returns URL)",
    "google_read_sheet": "Read existing spreadsheet range",
    "google_write_sheet": "Overwrite cells in existing spreadsheet",
    "google_append_sheet": "Append rows to existing spreadsheet",
    "google_create_doc": "CREATE new Google Doc",
    "google_read_doc": "Read existing Google Doc text",
    "google_append_doc": "Append text to existing Google Doc",
    "slack_fetch_thread": "Fetch Slack thread messages (read-only)",
    "slack_fetch_channel_history": "Fetch Slack channel history for time window",
    "slack_board_create_task": "Create task on Slack List board for channel",
    "slack_board_update_task": "Update Slack List task status/assignee",
    "slack_board_search_tasks": "Search tasks on Slack List board",
    "slack_board_get_task": "Get one Slack List task by id",
    "slack_board_comment": "Post comment in thread linked to board task",
    "grep_repo": "Search code in mirrored repo",
    "read_file": "Read file from mirrored repo",
    "get_pr": "Get GitHub pull request details",
    "run_company_script": "Run curated company script from manifest",
    "search_repo_docs": "Search indexed repo docs/runbooks (BM25)",
    "read_repo_doc": "Read full indexed doc by path",
    "list_repo_docs": "List indexed documentation paths",
    "athena_query": "Run Athena SQL query",
    "web_search": "Web search",
    "save_html_deck": "REQUIRED: save self-contained HTML slide deck (.alfred/exports/) — call after building HTML",
    "publish_html_artifact": "Publish HTML deck — /artifacts/s/{slug} with slug, or /artifacts/sha/{sha256} without",
}


def get_tool_description(tool_name: str) -> str:
    """One-line description for admin catalog and CLI."""
    if tool_name in _TOOL_DESCRIPTIONS:
        return _TOOL_DESCRIPTIONS[tool_name]
    # Fallback labels for tools without explicit planner descriptions
    _extras = {
        "list_my_prs": "List PRs opened by the authenticated user",
        "list_prs": "List pull requests for a repository",
        "list_repos": "List configured Git repositories",
        "get_pr_changes": "List files changed in a pull request",
        "git_log": "Git commit history for a file or path",
        "git_blame": "Git blame for a file",
        "git_show": "Show git object (commit) details",
        "git_prepare_branch": "Create/checkout a write branch from latest base",
        "write_file": "Write or overwrite a file in the repo workspace",
        "write_debug_script": "Write a debug script in the repo workspace",
        "run_debug_script": "Run a debug script in the repo workspace",
        "git_commit": "Commit staged changes locally",
        "git_push_branch": "Push branch to remote (requires confirmation)",
        "create_pull_request": "Open a pull request on GitHub",
        "query_graph": "Query Graphify code-structure graph",
        "list_jira_issues": "List JIRA issues (legacy alias)",
        "add_jira_comment": "Add JIRA comment (legacy alias)",
        "lookup_user_identity": "Resolve Slack/JIRA user identity",
        "build_workspace_identity_map": "Build Slack→JIRA identity map",
        "cloudwatch_query": "Query CloudWatch logs",
        "list_cloudwatch_log_groups": "List CloudWatch log groups",
        "list_company_scripts": "List company script packages",
        "read_company_script_file": "Read file from a script package",
        "write_company_script_file": "Write file in a script package",
        "create_company_script_package": "Scaffold a new script package",
        "list_schedules": "List scheduled jobs",
        "create_schedule": "Create a scheduled job",
        "update_schedule": "Update schedule cron/channel/instructions",
        "toggle_schedule": "Enable or disable a schedule",
        "delete_schedule": "Delete a scheduled job",
        "list_repo_docs": "List indexed documentation paths",
    }
    return _extras.get(tool_name, "See tool schema in registry")


def _artifact_manifest_section(allowed: list[str]) -> list[str]:
    if not set(allowed) <= {"save_html_deck", "publish_html_artifact"}:
        return []
    lines = [
        "",
        "**DELIVERY (mandatory — call a tool, do not only reply in prose):**",
    ]
    if "save_html_deck" in allowed:
        lines.append(
            "- `save_html_deck` — build HTML first, then pass the full file; "
            "default for every slide request"
        )
    if "publish_html_artifact" in allowed:
        lines.append(
            "- `publish_html_artifact` — publish/host/share; slug optional "
            "(slug → /artifacts/s/{slug}, no slug → /artifacts/sha/{sha256})"
        )
    lines.append(
        "- Claiming the deck is done without a successful tool call will be rejected."
    )
    return lines


def _group_tools(tool_names: list[str]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    for name in sorted(tool_names):
        domain = tool_domain(name)
        groups.setdefault(domain, []).append(name)
    return groups


def format_tool_catalog_for_planner(
    tool_names: list[str],
    *,
    max_tools: int = 40,
) -> str:
    """Markdown catalog grouped by domain for Tool Planner LLM."""
    names = sorted(set(tool_names))[:max_tools]
    if not names:
        return "(No tools available.)"

    lines = ["## Tool catalog (grouped by domain)", ""]
    for domain, domain_tools in sorted(_group_tools(names).items()):
        lines.append(f"### {domain}")
        for tool in domain_tools:
            desc = _TOOL_DESCRIPTIONS.get(tool, "See tool schema")
            lines.append(f"- `{tool}` — {desc}")
        lines.append("")
    return "\n".join(lines).strip()


def format_tool_manifest(
    allowed_tools: list[str],
    *,
    registered_tools: set[str] | frozenset[str] | None = None,
) -> str:
    """Explicit per-turn tool manifest for anti-hallucination."""
    allowed = sorted(set(allowed_tools))
    if not allowed:
        return "## Tool manifest\n\nNo tools available this turn."

    lines = [
        "## Tool manifest (this turn)",
        "",
        "You have EXACTLY these tools:",
    ]
    read_tools = [n for n in allowed if n in SLACK_BOARD_READ_TOOLS]
    write_tools = [n for n in allowed if n in SLACK_BOARD_WRITE_TOOLS]
    other_tools = [n for n in allowed if n not in read_tools and n not in write_tools]

    def _append_tools(label: str, names: list[str]) -> None:
        if not names:
            return
        lines.append("")
        lines.append(f"**{label}:**")
        for name in sorted(names):
            desc = _TOOL_DESCRIPTIONS.get(name, "")
            suffix = f" — {desc}" if desc else ""
            lines.append(f"- `{name}`{suffix}")

    _append_tools("READ (lookup / context)", read_tools)
    _append_tools("WRITE (mutations — required for create/update/comment)", write_tools)
    if other_tools:
        _append_tools("Other", other_tools)
    if not read_tools and not write_tools and not other_tools:
        for name in allowed:
            desc = _TOOL_DESCRIPTIONS.get(name, "")
            suffix = f" — {desc}" if desc else ""
            lines.append(f"- `{name}`{suffix}")

    lines.extend(_artifact_manifest_section(allowed))

    if registered_tools is not None:
        missing_common = [
            t
            for t in (
                "google_create_sheet",
                "jira_assign_issue",
                "transition_jira_issue",
                "slack_fetch_thread",
            )
            if t in registered_tools and t not in allowed
        ]
        if missing_common:
            lines.extend(["", "You do NOT have:", *[f"- `{t}`" for t in missing_common]])

    lines.extend(
        [
            "",
            "If the user needs a capability not listed above, say you don't have that tool — "
            "never simulate tool results in prose.",
        ]
    )
    return "\n".join(lines)


def all_plannable_tool_names() -> list[str]:
    """Canonical names used when building planner catalog."""
    from backend.tools.catalog import ARTIFACT_TOOLS

    return sorted(
        JIRA_TOOLS
        | GOOGLE_SHEET_TOOLS
        | GOOGLE_DOC_TOOLS
        | SLACK_TOOLS
        | GIT_TOOLS
        | REPO_DOC_TOOLS
        | AWS_TOOLS
        | WEB_TOOLS
        | COMPANY_SCRIPT_TOOLS
        | ARTIFACT_TOOLS
    )
