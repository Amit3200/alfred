"""Tests for GitHub webhook payload sanitization."""

from __future__ import annotations

from backend.github.sanitize import clean_github_comment, task_from_issue_comment
from backend.models.config import AlfredConfig, GitConfig, GitHubAppConfig


def _issue_comment_payload(
    *,
    body: str,
    login: str = "dev-user",
    user_type: str = "User",
    repo: str = "AcmeCorp/platform",
    number: int = 42,
) -> dict:
    return {
        "action": "created",
        "comment": {
            "id": 9001,
            "body": body,
            "user": {"login": login, "type": user_type},
        },
        "issue": {
            "number": number,
            "html_url": f"https://github.com/{repo}/pull/{number}",
            "pull_request": {"url": f"https://api.github.com/repos/{repo}/pulls/{number}"},
        },
        "repository": {"full_name": repo},
    }


def test_clean_github_comment_strips_mention():
    github = GitHubAppConfig(bot_login="alfred")
    assert clean_github_comment("@alfred review this PR", github=github) == "review this PR"
    assert clean_github_comment("@alfred can you review this PR?", github=github) == "can you review this PR?"
    assert clean_github_comment("@alfred[bot] summarize", github=github) == "summarize"


def test_task_from_issue_comment_matches_bot_slug():
    config = AlfredConfig(
        github=GitHubAppConfig(enabled=True, bot_login="alfred"),
        git=GitConfig(enabled=True, repos=["AcmeCorp/platform"]),
    )
    task = task_from_issue_comment(
        _issue_comment_payload(body="@alfred can you review this PR?"),
        config=config,
    )
    assert task is not None
    assert task.cleaned_intent.startswith("can you review this PR?")


def test_task_from_issue_comment_builds_pr_task():
    config = AlfredConfig(
        github=GitHubAppConfig(enabled=True),
        git=GitConfig(enabled=True, repos=["AcmeCorp/platform"]),
    )
    task = task_from_issue_comment(
        _issue_comment_payload(body="@alfred please review"),
        config=config,
    )
    assert task is not None
    assert task.source == "git"
    assert task.channel_id == "AcmeCorp/platform"
    assert task.thread_ts == "42"
    assert "https://github.com/AcmeCorp/platform/pull/42" in task.cleaned_intent
    assert task.metadata["pr_number"] == 42


def test_task_from_issue_comment_ignores_non_pr():
    config = AlfredConfig(github=GitHubAppConfig(enabled=True))
    payload = _issue_comment_payload(body="@alfred hi")
    payload["issue"].pop("pull_request")
    assert task_from_issue_comment(payload, config=config) is None


def test_task_from_issue_comment_ignores_bot():
    config = AlfredConfig(github=GitHubAppConfig(enabled=True, bot_login="alfred"))
    payload = _issue_comment_payload(body="@alfred review", login="alfred[bot]", user_type="Bot")
    assert task_from_issue_comment(payload, config=config) is None


def test_task_from_issue_comment_respects_repo_allowlist():
    config = AlfredConfig(
        github=GitHubAppConfig(enabled=True, allowed_repos=["OtherOrg/other"]),
        git=GitConfig(repos=["OtherOrg/other"]),
    )
    assert task_from_issue_comment(
        _issue_comment_payload(body="@alfred review", repo="AcmeCorp/platform"),
        config=config,
    ) is None
