"""Render structured assistant responses for Slack, UI, and CLI."""

from __future__ import annotations

from typing import Literal

from backend.formatting.strategies import (
    KIND_FORMATTERS,
    format_for_github,
    format_for_slack,
    format_for_ui,
)
from backend.models.response import AssistantResponse, ResponsePayload

Channel = Literal["slack", "ui", "cli", "github"]

# Investigation loops may attach tool payloads while the model also wrote prose.
# Always prefer the prose for human-facing channels (e.g. GitHub PR comments).
_PROSE_OVERRIDES_STRUCTURED = frozenset(
    {"file_content", "code_grep", "git_log", "git_blame", "git_show"}
)


def render_for_channel(response: AssistantResponse, channel: Channel) -> str:
    """Render a structured response as plain text for the given channel."""
    payload = response.payload
    prose = (response.text or "").strip()
    if prose and payload.kind in _PROSE_OVERRIDES_STRUCTURED:
        return _format_text(prose, channel)
    if payload.kind == "text":
        text = str(payload.data.get("text") or response.text or "")
        return _format_text(text, channel)
    if payload.kind == "error":
        message = str(payload.data.get("message") or response.text or "Something went wrong.")
        return _format_text(message, channel)

    # Dispatch to Strategy Registry
    if payload.kind in KIND_FORMATTERS:
        return KIND_FORMATTERS[payload.kind].render(payload.data, slack=(channel == "slack"))

    # Generic UI / File context formatting
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
    if payload.kind == "google_sheet":
        return _render_google_sheet(payload, channel)
    if payload.kind == "google_doc":
        return _render_google_doc(payload, channel)

    return _format_text(response.text or "", channel)


def render_turn(payload: ResponsePayload | None, content: str, channel: Channel) -> str:
    """Render a stored session turn (payload preferred, content fallback)."""
    if payload is not None:
        return render_for_channel(AssistantResponse(payload=payload, text=content), channel)
    return _format_text(content, channel)


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


def _render_google_sheet(payload: ResponsePayload, channel: Channel) -> str:
    action = str(payload.data.get("action") or "")
    spreadsheet_id = str(payload.data.get("spreadsheet_id") or "")
    if action == "read":
        rows = payload.data.get("rows") or []
        range_a1 = str(payload.data.get("range") or "")
        header = f"Sheet `{spreadsheet_id}` · `{range_a1}` ({len(rows)} rows)"
        if not rows:
            return f"{header}\n(no data)"
        preview = rows[:20]
        lines = [header, ""]
        for row in preview:
            if channel == "slack":
                lines.append("• " + " | ".join(str(cell) for cell in row))
            else:
                lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
        if len(rows) > 20:
            lines.append(f"… and {len(rows) - 20} more rows")
        return "\n".join(lines)
    updated = payload.data.get("updated_cells") or payload.data.get("updated_rows") or 0
    range_a1 = str(payload.data.get("range") or "")
    verb = "Updated" if action == "write" else "Appended to"
    return f"{verb} `{spreadsheet_id}` · `{range_a1}` ({updated} cells/rows updated)."


def _render_google_doc(payload: ResponsePayload, channel: Channel) -> str:
    action = str(payload.data.get("action") or "")
    document_id = str(payload.data.get("document_id") or "")
    if action == "read":
        title = str(payload.data.get("title") or document_id)
        text = str(payload.data.get("text") or "")
        preview = text[:4000]
        suffix = "\n… (truncated)" if len(text) > 4000 else ""
        return f"**{title}**\n\n{preview}{suffix}".strip()
    if action == "create":
        title = str(payload.data.get("title") or "")
        url = str(payload.data.get("url") or "")
        if url:
            return f"Created doc **{title}**: {url}"
        return f"Created doc **{title}** (`{document_id}`)."
    appended = payload.data.get("appended_chars") or 0
    return f"Appended {appended} characters to doc `{document_id}`."


def _format_text(text: str, channel: Channel) -> str:
    if channel == "slack":
        return format_for_slack(text)
    if channel == "github":
        return format_for_github(text)
    if channel == "ui":
        return format_for_ui(text)
    return text
