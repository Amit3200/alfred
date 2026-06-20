"""Format Git API results for Slack and CLI."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from backend.git.api import PullRequestSummary


def format_prs(prs: list[PullRequestSummary], *, slack: bool = True, state: str = "open") -> str:
    if not prs:
        state_label = state if state != "all" else ""
        prefix = f"{state_label} " if state_label else ""
        return f"No {prefix.strip()} pull requests found.".strip()

    count = len(prs)
    state_word = state if state in ("open", "closed") else "matching"
    header_text = f"{count} {state_word} PR{'s' if count != 1 else ''}"
    header = f"*{header_text}*" if slack else f"**{header_text}**"

    by_repo: dict[str, list[PullRequestSummary]] = defaultdict(list)
    for pr in prs:
        short = pr.repo.rsplit("/", 1)[-1] if pr.repo else "unknown"
        by_repo[short].append(pr)

    lines = [header]
    if not slack:
        lines.append("")
    for repo_short in sorted(by_repo.keys()):
        if slack:
            lines.append(f"\n`{repo_short}`")
        else:
            lines.append(f"### {repo_short}")
        for pr in sorted(by_repo[repo_short], key=lambda item: item.number, reverse=True):
            lines.append(_format_pr_bullet(pr, slack=slack))
        if not slack:
            lines.append("")

    return "\n".join(lines).strip()


def format_pr_detail(data: dict[str, Any], *, slack: bool = True) -> str:
    number = data.get("number")
    title = data.get("title") or "Untitled"
    repo = data.get("repo") or ""
    repo_short = repo.rsplit("/", 1)[-1] if repo else ""
    url = str(data.get("url") or "")
    state = str(data.get("state") or "")
    author = str(data.get("author") or "")
    head = data.get("head")
    base = data.get("base")
    draft = data.get("draft")

    if slack and url:
        title_line = f"<{url}|#{number} {title}>"
    elif url:
        title_line = f"[#{number} {title}]({url})"
    else:
        title_line = f"#{number} {title}"

    header = f"*PR in `{repo_short}`*" if slack else f"**PR in `{repo_short}`**"
    lines = [header, title_line]
    meta = []
    if state:
        meta.append(state)
    if author:
        meta.append(f"by `{author}`")
    if draft:
        meta.append("draft")
    if meta:
        lines.append(" · ".join(meta))
    if head and base:
        lines.append(f"`{head}` → `{base}`")

    body = (data.get("body") or "").strip()
    if body:
        snippet = body if len(body) <= 400 else body[:397] + "..."
        lines.append(f"\n{snippet}")

    return "\n".join(lines).strip()


def _format_pr_bullet(pr: PullRequestSummary, *, slack: bool) -> str:
    draft = " _(draft)_" if pr.draft else ""
    label = f"#{pr.number} {pr.title}"
    if slack and pr.url:
        return f"• <{pr.url}|{label}>{draft}"
    if pr.url:
        return f"- [{label}]({pr.url}){draft}"
    return f"- {label}{draft}"
