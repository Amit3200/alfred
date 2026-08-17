"""Tests for Git PR Slack formatting."""

from __future__ import annotations

from backend.integrations.git.api import PullRequestSummary
from backend.formatting.strategies import format_pr_detail, format_prs


def _sample_prs() -> list[PullRequestSummary]:
    return [
        PullRequestSummary(
            number=1685,
            title="Thanks page",
            state="open",
            repo="AcmeCorp/platform",
            author="alice",
            url="https://github.com/AcmeCorp/platform/pull/1685",
        ),
        PullRequestSummary(
            number=91,
            title="SQS Consumer Support Added",
            state="open",
            repo="AcmeCorp/adhocs",
            author="alice",
            url="https://github.com/AcmeCorp/adhocs/pull/91",
        ),
        PullRequestSummary(
            number=16,
            title="Flx tests",
            state="open",
            repo="AcmeCorp/adhocs",
            author="alice",
            url="https://github.com/AcmeCorp/adhocs/pull/16",
        ),
    ]


def test_format_prs_slack_groups_by_repo():
    text = format_prs(_sample_prs(), slack=True)
    assert "*3 open PRs*" in text
    assert "`platform`" in text
    assert "`adhocs`" in text
    assert "<https://github.com/AcmeCorp/platform/pull/1685|#1685 Thanks page>" in text
    assert "There is an open PR" not in text


def test_format_prs_empty():
    assert "No open pull requests" in format_prs([], slack=True)


def test_format_prs_markdown_groups_by_repo():
    text = format_prs(_sample_prs(), slack=False)
    assert "**3 open PRs**" in text
    assert "### platform" in text
    assert "### adhocs" in text
    assert "[#1685 Thanks page](https://github.com/AcmeCorp/platform/pull/1685)" in text
    assert "<https://" not in text


def test_format_pr_detail_markdown():
    text = format_pr_detail(
        {
            "number": 91,
            "title": "SQS Consumer Support Added",
            "state": "open",
            "repo": "AcmeCorp/adhocs",
            "author": "alice",
            "url": "https://github.com/AcmeCorp/adhocs/pull/91",
            "head": "feature/sqs",
            "base": "main",
            "body": "Adds consumer",
            "draft": False,
        },
        slack=False,
    )
    assert "**PR in `adhocs`**" in text
    assert "[#91 SQS Consumer Support Added](https://github.com/AcmeCorp/adhocs/pull/91)" in text


def test_format_pr_detail_slack():
    text = format_pr_detail(
        {
            "number": 91,
            "title": "SQS Consumer Support Added",
            "state": "open",
            "repo": "AcmeCorp/adhocs",
            "author": "alice",
            "url": "https://github.com/AcmeCorp/adhocs/pull/91",
            "head": "feature/sqs",
            "base": "main",
            "body": "Adds consumer",
            "draft": False,
        },
        slack=True,
    )
    assert "*PR in `adhocs`*" in text
    assert "<https://github.com/AcmeCorp/adhocs/pull/91|#91 SQS Consumer Support Added>" in text
    assert "`feature/sqs` → `main`" in text
