"""Tests for channel rendering of structured responses."""

from __future__ import annotations

from backend.integrations.git.api import PullRequestSummary
from backend.formatting.render import render_for_channel
from backend.models.response import AssistantResponse
from backend.tools.result import ToolResult


def test_render_pr_list_slack():
    result = ToolResult.pr_list(
        [
            PullRequestSummary(
                number=1,
                title="Fix",
                state="open",
                repo="org/repo",
                author="alice",
                url="https://github.com/org/repo/pull/1",
            )
        ],
        state="open",
    )
    response = AssistantResponse.structured(result.kind, result.data)
    text = render_for_channel(response, "slack")
    assert "*1 open PR*" in text
    assert "<https://github.com/org/repo/pull/1|#1 Fix>" in text


def test_render_pr_list_ui():
    result = ToolResult.pr_list(
        [
            PullRequestSummary(
                number=1,
                title="Fix",
                state="open",
                repo="org/repo",
                author="alice",
                url="https://github.com/org/repo/pull/1",
            )
        ],
        state="open",
    )
    response = AssistantResponse.structured(result.kind, result.data)
    text = render_for_channel(response, "ui")
    assert "**1 open PR**" in text
    assert "[#1 Fix](https://github.com/org/repo/pull/1)" in text


def test_render_pr_detail_ui():
    detail = {
        "number": 91,
        "title": "Feature",
        "state": "open",
        "repo": "org/app",
        "author": "bob",
        "url": "https://github.com/org/app/pull/91",
        "head": "feat",
        "base": "main",
        "body": "Adds feature",
        "draft": False,
    }
    response = AssistantResponse.structured("pr_detail", {"pr": detail})
    text = render_for_channel(response, "ui")
    assert "[#91 Feature](https://github.com/org/app/pull/91)" in text


def test_render_prefers_prose_over_file_content_on_github():
    response = AssistantResponse.structured(
        "file_content",
        {"repo": "org/app", "path": "handler.ts", "content": "export const x = 1;"},
        text="## 1. Executive Summary\n**PR Objective:** Fix webhook logging",
    )
    text = render_for_channel(response, "github")
    assert "Executive Summary" in text
    assert "export const x = 1" not in text
