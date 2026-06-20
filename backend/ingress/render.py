"""Render structured assistant responses for Slack, UI, and CLI."""

from __future__ import annotations

from typing import Literal

from backend.git.api import PullRequestSummary
from backend.ingress.git_format import format_pr_detail, format_prs
from backend.ingress.slack_format import format_for_slack
from backend.ingress.ui_format import format_for_ui
from backend.models.response import AssistantResponse, ResponsePayload
from backend.tools.result import pr_summary_from_dict

Channel = Literal["slack", "ui", "cli"]


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


def _format_text(text: str, channel: Channel) -> str:
    if channel == "slack":
        return format_for_slack(text)
    if channel == "ui":
        return format_for_ui(text)
    return text
