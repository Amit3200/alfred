"""Write tool catalog — which tools require confirmation vs audit-only."""

from __future__ import annotations

from typing import Any

# Mutate external systems or publish changes — require explicit user confirmation.
CONFIRMATION_REQUIRED_TOOLS: frozenset[str] = frozenset(
    {
        # Git publish
        "git_push_branch",
        "create_pull_request",
        # JIRA writes
        "transition_jira_issue",
        "add_jira_comment",
        "link_jira_issue",
        "jira_update_issue",
        "jira_add_comment",
        "jira_create_issue",
        "jira_assign_issue",
        # Google writes
        "google_create_sheet",
        "google_write_sheet",
        "google_append_sheet",
        "google_create_doc",
        "google_append_doc",
        # Slack Lists board writes
        "slack_board_create_task",
        "slack_board_update_task",
        "slack_board_comment",
        # Schedules
        "create_schedule",
        "update_schedule",
        "delete_schedule",
        "toggle_schedule",
    }
)

# Local repo/workspace mutations — audited but no confirmation (reversible before push).
WRITE_STAGING_TOOLS: frozenset[str] = frozenset(
    {
        "git_prepare_branch",
        "write_file",
        "write_debug_script",
        "git_commit",
        "write_company_script_file",
        "create_company_script_package",
    }
)

ALL_WRITE_TOOLS: frozenset[str] = CONFIRMATION_REQUIRED_TOOLS | WRITE_STAGING_TOOLS


def requires_confirmation(tool_name: str) -> bool:
    return tool_name in CONFIRMATION_REQUIRED_TOOLS


def is_write_tool(tool_name: str) -> bool:
    return tool_name in ALL_WRITE_TOOLS


def write_tool_names() -> list[str]:
    return sorted(ALL_WRITE_TOOLS)


def tool_action_summary(tool_name: str, arguments: dict[str, Any]) -> str:
    """Human-readable one-liner for confirmation prompts."""
    args = arguments or {}
    if tool_name == "git_push_branch":
        return f"Push branch `{args.get('branch') or '(current)'}` on repo `{args.get('repo', '?')}`"
    if tool_name == "create_pull_request":
        return (
            f"Open PR `{args.get('title', '?')}` "
            f"(`{args.get('head', '?')}` → `{args.get('base') or 'main'}`) on `{args.get('repo', '?')}`"
        )
    if tool_name == "git_commit":
        return f"Commit on `{args.get('repo', '?')}`: {str(args.get('message', ''))[:120]}"
    if tool_name in ("write_file", "write_debug_script"):
        return f"Write file `{args.get('path') or args.get('filename', '?')}` in `{args.get('repo', '?')}`"
    if tool_name == "write_company_script_file":
        return f"Write company script file `{args.get('relative_path', '?')}` under `.alfred/scripts/`"
    if tool_name == "create_company_script_package":
        return f"Create company script package `{args.get('package_path', '?')}` under `.alfred/scripts/`"
    if tool_name == "git_prepare_branch":
        return f"Create branch `{args.get('branch_name', '?')}` from latest `{args.get('base_branch') or 'main'}`"
    if tool_name == "jira_create_issue":
        project = str(args.get("project") or "").strip() or "?"
        title = str(args.get("summary") or "").strip()
        if title:
            return f"JIRA create `{project}` · {title[:100]}"
        return f"JIRA create issue in `{project}`"
    if tool_name == "jira_update_issue":
        key = args.get("issue_key") or "?"
        title = str(args.get("summary") or "").strip()
        if title:
            return f"JIRA update `{key}` · {title[:100]}"
        return f"JIRA update `{key}`"
    if tool_name.startswith("jira") or tool_name in (
        "transition_jira_issue",
        "add_jira_comment",
        "link_jira_issue",
    ):
        key = args.get("issue_key") or args.get("key") or "?"
        return f"JIRA write `{tool_name}` on `{key}`"
    if tool_name.startswith("google_"):
        target = args.get("spreadsheet_id") or args.get("document_id") or "?"
        return f"Google `{tool_name}` on `{target}`"
    if tool_name.startswith("slack_board_"):
        ref = args.get("ticket_ref") or args.get("title") or "?"
        return f"Slack board `{tool_name}` for `{ref}`"
    if tool_name.startswith(("create_schedule", "update_schedule", "delete_schedule", "toggle_schedule")):
        return f"Schedule `{tool_name}` job `{args.get('job_id') or args.get('name', '?')}`"
    return f"Execute write tool `{tool_name}`"
