"""Shared processor constants and response helpers."""

from __future__ import annotations

from typing import Any

from backend.formatting.render import Channel
from backend.models.response import AssistantResponse
from backend.models.task import Task
from backend.tools.result import ToolResult

STRUCTURED_TOOL_KINDS = frozenset(
    {
        "pr_list",
        "pr_detail",
        "pr_created",
        "repo_list",
        "code_grep",
        "file_content",
        "git_log",
        "git_blame",
        "git_show",
        "jira_list",
        "jira_detail",
        "jira_action",
        "athena_query",
        "cloudwatch_query",
        "cloudwatch_log_groups",
        "google_sheet",
        "google_doc",
        "web_search",
        "doc_search",
        "doc_content",
        "doc_answer",
    }
)

_MISSING_TOOLS_REPLY_MARKERS = (
    "don't currently have jira",
    "do not currently have jira",
    "don't have jira",
    "no jira ticket creation",
    "jira tools are not available",
    "jira tools aren't available",
    "only have athena",
)


def _looks_like_missing_tools_reply(raw: str) -> bool:
    lower = (raw or "").lower()
    return any(marker in lower for marker in _MISSING_TOOLS_REPLY_MARKERS)


def _tool_result_to_response(result: ToolResult) -> AssistantResponse | None:
    if result.kind == "user_identity":
        from backend.integrations.identity.user_identity import format_user_identity_result

        return AssistantResponse.from_text(format_user_identity_result(result.data))
    if result.kind == "slack_messages":
        text = str(result.data.get("text") or "").strip()
        if text:
            return AssistantResponse.from_text(text)
        count = int(result.data.get("message_count") or 0)
        return AssistantResponse.from_text(f"Fetched {count} Slack message(s).")
    if result.kind == "slack_board_task":
        from backend.routing.slack_board.direct import (
            format_board_task_created,
            format_board_task_updated,
        )

        data = result.data or {}
        if data.get("updated"):
            return AssistantResponse.from_text(format_board_task_updated(data))
        return AssistantResponse.from_text(
            format_board_task_created(
                data,
                severity=str(data.get("severity") or ""),
                assignee_user_id=str(data.get("assignee_user_id") or ""),
            )
        )
    if result.kind == "slack_board_search":
        rows = list((result.data or {}).get("results") or [])
        if not rows:
            return AssistantResponse.from_text("No matching board tasks found.")
        lines = [f"Found **{len(rows)}** board task(s):"]
        for row in rows[:10]:
            if not isinstance(row, dict):
                continue
            display = row.get("display_id") or row.get("record_id") or "Task"
            title = row.get("title") or row.get("formatted") or ""
            status = row.get("status") or ""
            line = f"- **{display}**"
            if title:
                line += f" — {title}"
            if status:
                line += f" (`{status}`)"
            lines.append(line)
        return AssistantResponse.from_text("\n".join(lines))
    if result.kind == "slack_board_comment":
        return AssistantResponse.from_text("Posted comment on the board task thread.")
    if result.kind == "html_artifact_published":
        from backend.artifacts.formatting import format_published_artifact_slack

        public_base = ""
        return AssistantResponse.from_text(
            format_published_artifact_slack(result.data, public_base_url=public_base)
        )
    if result.kind == "html_deck_saved":
        from backend.artifacts.formatting import format_saved_html_deck_slack

        return AssistantResponse.from_text(format_saved_html_deck_slack(result.data))
    if result.kind in STRUCTURED_TOOL_KINDS:
        return AssistantResponse.structured(result.kind, result.data)
    if result.kind == "error":
        return AssistantResponse.error(str(result.data.get("message") or "Tool failed."))
    return None


def _task_channel(task: Task) -> Channel:
    if task.source == "slack":
        return "slack"
    if task.source == "ui":
        return "ui"
    if task.source == "git":
        return "github"
    return "cli"


def clean_message_text(text: str) -> str:
    from backend.integrations.slack.sanitize import clean_slack_text

    return clean_slack_text(text)


def _unified_metadata_patch(
    tool_name: str,
    args: dict[str, Any],
    result: Any,
) -> dict[str, Any] | None:
    if result.kind == "error":
        return None

    # JIRA tools patch
    jira_patch = {}
    issue = result.data.get("issue") or result.data
    key = args.get("issue_key") or args.get("key") or (isinstance(issue, dict) and issue.get("key"))
    if key and (tool_name.startswith("jira") or tool_name in ("get_jira_issue", "create_jira_issue", "transition_jira_issue", "comment_jira_issue", "add_jira_comment")):
        jira_patch["active_jira_ticket"] = str(key)

    # Git tools patch
    from backend.routing.git.context import metadata_patch_for_tool_result
    git_patch = metadata_patch_for_tool_result(tool_name, args, result) or {}

    if tool_name == "save_html_deck" and getattr(result, "kind", "") == "html_deck_saved":
        from backend.routing.html_slides_delivery import html_deck_session_metadata_patch

        deck_patch = html_deck_session_metadata_patch(getattr(result, "data", {}) or {})
        return {**jira_patch, **git_patch, **deck_patch}

    if tool_name == "publish_html_artifact" and getattr(result, "kind", "") == "html_artifact_published":
        data = getattr(result, "data", {}) or {}
        return {
            **jira_patch,
            **git_patch,
            "pending_publish": False,
            "last_published_slug": str(data.get("slug") or ""),
            "last_published_url": str(data.get("share_url") or data.get("slug_url") or ""),
        }

    return {**jira_patch, **git_patch}
