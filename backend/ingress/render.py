"""Render structured assistant responses for Slack, UI, and CLI."""

from __future__ import annotations

from typing import Literal

from backend.git.api import PullRequestSummary
from backend.ingress.git_format import format_pr_detail, format_prs
from backend.ingress.slack_format import format_for_slack
from backend.ingress.ui_format import format_for_ui
from backend.models.response import AssistantResponse, ResponsePayload
from backend.tools.result import pr_summary_from_dict

Channel = Literal["slack", "ui", "cli", "github"]


def render_for_channel(response: AssistantResponse, channel: Channel) -> str:
    """Render a structured response as plain text for the given channel."""
    payload = response.payload
    if payload.kind == "text":
        text = str(payload.data.get("text") or response.text or "")
        return _format_text(text, channel)
    if payload.kind == "error":
        message = str(payload.data.get("message") or response.text or "Something went wrong.")
        return _format_text(message, channel)
    if payload.kind == "pr_list":
        return _render_pr_list(payload, channel)
    if payload.kind == "pr_detail":
        return _render_pr_detail(payload, channel)
    if payload.kind == "repo_list":
        return _render_repo_list(payload, channel)
    if payload.kind == "code_grep":
        return _render_code_grep(payload, channel)
    if payload.kind == "file_content":
        return _render_file_content(payload, channel)
    if payload.kind == "git_log":
        return _render_git_log(payload, channel)
    if payload.kind == "git_blame":
        return _render_git_blame(payload, channel)
    if payload.kind == "git_show":
        return _render_git_show(payload, channel)
    return _format_text(response.text or "", channel)


def render_turn(payload: ResponsePayload | None, content: str, channel: Channel) -> str:
    """Render a stored session turn (payload preferred, content fallback)."""
    if payload is not None:
        return render_for_channel(AssistantResponse(payload=payload, text=content), channel)
    return _format_text(content, channel)


def _render_pr_list(payload: ResponsePayload, channel: Channel) -> str:
    prs = [pr_summary_from_dict(item) for item in payload.data.get("prs") or []]
    state = str(payload.data.get("state") or "open")
    if not prs:
        state_label = state if state != "all" else ""
        prefix = f"{state_label} " if state_label else ""
        return f"No {prefix.strip()} pull requests found.".strip()
    return format_prs(prs, slack=channel == "slack", state=state)


def _render_pr_detail(payload: ResponsePayload, channel: Channel) -> str:
    detail = payload.data.get("pr") or {}
    return format_pr_detail(detail, slack=channel == "slack")


def _render_repo_list(payload: ResponsePayload, channel: Channel) -> str:
    repos = [str(repo) for repo in payload.data.get("repos") or []]
    if not repos:
        return "No repositories configured or accessible."
    if channel == "slack":
        return "\n".join(f"• `{repo}`" for repo in repos)
    return "\n".join(f"- `{repo}`" for repo in repos)


def _render_code_grep(payload: ResponsePayload, channel: Channel) -> str:
    repo = str(payload.data.get("repo") or "")
    pattern = str(payload.data.get("pattern") or "")
    matches = payload.data.get("matches") or []
    if not matches:
        return f"No matches for `{pattern}` in `{repo}`."
    lines = [f"**Matches in `{repo}`**" if channel == "ui" else f"*Matches in `{repo}`*"]
    for item in matches:
        path = item.get("path", "")
        line_no = item.get("line", "")
        text = item.get("text", "")
        if channel == "slack":
            lines.append(f"• `{path}:{line_no}` — {text}")
        else:
            lines.append(f"- `{path}:{line_no}` — {text}")
    return "\n".join(lines)


def _render_file_content(payload: ResponsePayload, channel: Channel) -> str:
    repo = str(payload.data.get("repo") or "")
    path = str(payload.data.get("path") or "")
    start = int(payload.data.get("start_line") or 1)
    content = str(payload.data.get("content") or "")
    header = f"```{path}\n" if channel != "slack" else f"`{repo}/{path}` (from line {start}):\n```\n"
    return f"{header}{content}\n```".strip()


def _render_git_log(payload: ResponsePayload, channel: Channel) -> str:
    repo = str(payload.data.get("repo") or "")
    commits = payload.data.get("commits") or []
    if not commits:
        return f"No commits found in `{repo}`."
    title = f"Recent commits in `{repo}`"
    body = "\n".join(f"- {line}" for line in commits)
    return f"{title}\n{body}"


def _render_git_blame(payload: ResponsePayload, channel: Channel) -> str:
    repo = str(payload.data.get("repo") or "")
    path = str(payload.data.get("path") or "")
    lines = payload.data.get("lines") or []
    header = f"Blame `{repo}/{path}`"
    body = "\n".join(lines[:40])
    return f"{header}\n```\n{body}\n```"


def _render_git_show(payload: ResponsePayload, channel: Channel) -> str:
    repo = str(payload.data.get("repo") or "")
    ref = str(payload.data.get("ref") or "")
    output = str(payload.data.get("output") or "")
    header = f"Commit `{ref}` in `{repo}`"
    return f"{header}\n```\n{output.strip()}\n```"


def _format_text(text: str, channel: Channel) -> str:
    if channel == "slack":
        return format_for_slack(text)
    if channel in ("ui", "github"):
        return format_for_ui(text)
    return text
