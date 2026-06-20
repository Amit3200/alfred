"""Structured tool results — JSON for the agent loop, rendered at channel boundaries."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from backend.git.api import PullRequestSummary


@dataclass
class ToolResult:
    kind: str
    data: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps({"kind": self.kind, "data": self.data}, default=str)

    @classmethod
    def error(cls, message: str) -> ToolResult:
        return cls(kind="error", data={"message": message})

    @classmethod
    def pr_list(cls, prs: list[PullRequestSummary], *, state: str = "open") -> ToolResult:
        return cls(
            kind="pr_list",
            data={"state": state, "prs": [pr_summary_to_dict(pr) for pr in prs]},
        )

    @classmethod
    def pr_detail(cls, detail: dict[str, Any]) -> ToolResult:
        return cls(kind="pr_detail", data={"pr": detail})

    @classmethod
    def repo_list(cls, repos: list[str]) -> ToolResult:
        return cls(kind="repo_list", data={"repos": repos})


def pr_summary_to_dict(pr: PullRequestSummary) -> dict[str, Any]:
    return {
        "number": pr.number,
        "title": pr.title,
        "state": pr.state,
        "repo": pr.repo,
        "author": pr.author,
        "url": pr.url,
        "draft": pr.draft,
    }


def pr_summary_from_dict(data: dict[str, Any]) -> PullRequestSummary:
    return PullRequestSummary(
        number=int(data["number"]),
        title=str(data.get("title") or ""),
        state=str(data.get("state") or "open"),
        repo=str(data.get("repo") or ""),
        author=str(data.get("author") or ""),
        url=str(data.get("url") or ""),
        draft=bool(data.get("draft")),
    )
