"""Parse GitHub webhook payloads into Alfred tasks."""

from __future__ import annotations

import re
from typing import Any

from backend.models.config import AlfredConfig, GitHubAppConfig
from backend.models.task import Task

_BOT_SUFFIX_RE = re.compile(r"\[bot\]$", re.IGNORECASE)


def _mention_slugs(github: GitHubAppConfig) -> list[str]:
    slugs = {"alfred"}
    bot = (github.bot_login or "").strip()
    if bot:
        slugs.add(bot)
    return sorted(slugs, key=len, reverse=True)


def _mention_re(github: GitHubAppConfig) -> re.Pattern[str]:
    parts = "|".join(re.escape(slug) for slug in _mention_slugs(github))
    return re.compile(rf"@(?:{parts})(?:\[bot\])?(?=\s|[,.!?]|$)", re.IGNORECASE)


def _mention_prefix_re(github: GitHubAppConfig) -> re.Pattern[str]:
    parts = "|".join(re.escape(slug) for slug in _mention_slugs(github))
    return re.compile(rf"^@?(?:{parts})(?:\[bot\])?[,:]?\s+", re.IGNORECASE)


def clean_github_comment(raw_text: str, *, github: GitHubAppConfig | None = None) -> str:
    github = github or GitHubAppConfig()
    text = _mention_re(github).sub("", raw_text or "").strip()
    text = _mention_prefix_re(github).sub("", text).strip()
    return text


def repo_allowed(full_name: str, config: AlfredConfig) -> bool:
    allowed = config.github.allowed_repos or config.git.repos or []
    if not allowed:
        return True
    normalized = {entry.strip().lower() for entry in allowed if entry.strip()}
    return full_name.lower() in normalized


def task_from_issue_comment(
    payload: dict[str, Any],
    *,
    config: AlfredConfig,
) -> Task | None:
    """Build a Task from an issue_comment webhook payload (PR comments only)."""
    if payload.get("action") != "created":
        return None

    comment = payload.get("comment") or {}
    user = comment.get("user") or {}
    login = str(user.get("login") or "")
    if user.get("type") == "Bot" or _is_bot_login(login, config.github):
        return None

    issue = payload.get("issue") or {}
    if issue.get("pull_request") is None:
        return None

    repository = payload.get("repository") or {}
    repo = str(repository.get("full_name") or "")
    if not repo or not repo_allowed(repo, config):
        return None

    number = int(issue.get("number") or 0)
    if number <= 0:
        return None

    raw_text = str(comment.get("body") or "")
    mention = _mention_re(config.github)
    if not mention.search(raw_text):
        return None

    cleaned = clean_github_comment(raw_text, github=config.github)
    if not cleaned:
        cleaned = "review this pull request"

    pr_url = str(issue.get("html_url") or f"https://github.com/{repo}/pull/{number}")
    intent = f"{cleaned}\n\n{pr_url}"

    return Task(
        source="git",
        user_id=login,
        channel_id=repo,
        thread_ts=str(number),
        raw_text=raw_text,
        cleaned_intent=intent,
        metadata={
            "github_event": "issue_comment",
            "comment_id": comment.get("id"),
            "pr_number": number,
            "pr_url": pr_url,
            "repository": repo,
        },
    )


def _is_bot_login(login: str, github: GitHubAppConfig) -> bool:
    if not login:
        return False
    bot_login = (github.bot_login or "alfred").strip()
    candidate = login.lower()
    if _BOT_SUFFIX_RE.search(login):
        if candidate == bot_login.lower():
            return True
        if candidate == f"{bot_login.lower()}[bot]":
            return True
    return candidate == bot_login.lower()
