"""Run a PR review and optionally post it as a GitHub comment."""

from __future__ import annotations

import re
from typing import Any

from backend.config_manager import ConfigManager
from backend.github.client import post_pull_request_comment
from backend.ingress.processor import TaskProcessor
from backend.ingress.render import render_for_channel
from backend.models.task import Task

_PR_URL_RE = re.compile(r"^https://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pull/(?P<number>\d+)(?:/.*)?$")
_PR_HASH_RE = re.compile(r"^(?P<repo>[^/\s]+/[^#\s]+)#(?P<number>\d+)$")


def parse_pr_ref(ref: str) -> tuple[str, int, str]:
    """Return (repo_slug, pr_number, html_url) from a PR URL or org/repo#123."""
    text = (ref or "").strip()
    if not text:
        raise ValueError("PR reference is required (URL or org/repo#123)")

    if match := _PR_URL_RE.match(text):
        repo = f"{match.group('owner')}/{match.group('repo')}"
        number = int(match.group("number"))
        return repo, number, text.split("?", 1)[0]

    if match := _PR_HASH_RE.match(text):
        repo = match.group("repo")
        number = int(match.group("number"))
        return repo, number, f"https://github.com/{repo}/pull/{number}"

    raise ValueError(f"Unrecognized PR reference: {ref!r} (use URL or org/repo#123)")


def build_github_review_task(
    *,
    repo: str,
    number: int,
    pr_url: str,
    intent: str = "review this pull request",
    user_id: str = "cli",
) -> Task:
    return Task(
        source="git",
        user_id=user_id,
        channel_id=repo,
        thread_ts=str(number),
        raw_text=intent,
        cleaned_intent=f"{intent.strip()}\n\n{pr_url}",
        metadata={
            "github_event": "cli_review",
            "pr_number": number,
            "pr_url": pr_url,
            "repository": repo,
        },
    )


def run_github_pr_review(
    manager: ConfigManager,
    pr_ref: str,
    *,
    intent: str = "review this pull request",
    post: bool = True,
    processor_factory: Any | None = None,
) -> tuple[str, str]:
    """Process a PR review and optionally post to GitHub. Returns (body, status)."""
    repo, number, pr_url = parse_pr_ref(pr_ref)
    config, _ = manager.load_merged()
    if not config.git.enabled or not config.git.token:
        raise RuntimeError("Git integration and token must be configured to review/post on GitHub.")

    task = build_github_review_task(
        repo=repo,
        number=number,
        pr_url=pr_url,
        intent=intent,
    )
    processor = (
        processor_factory()
        if processor_factory
        else TaskProcessor(config, data_dir=manager.data_dir)
    )
    response = processor.process(task)
    body = render_for_channel(response, "github")
    if not body.strip():
        raise RuntimeError("Review produced an empty response.")

    if post:
        post_pull_request_comment(config, repo=repo, number=number, body=body)
        status = f"posted comment on {repo}#{number}"
    else:
        status = f"review ready for {repo}#{number} (not posted)"

    return body, status
