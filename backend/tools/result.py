"""Structured tool results — JSON for the agent loop, rendered at channel boundaries."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from backend.git.api import PullRequestSummary
from backend.jira.api import JiraIssueSummary


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

    @classmethod
    def jira_list(cls, issues: list[JiraIssueSummary]) -> ToolResult:
        return cls(
            kind="jira_list",
            data={"issues": [jira_summary_to_dict(issue) for issue in issues]},
        )

    @classmethod
    def jira_detail(cls, detail: dict[str, Any]) -> ToolResult:
        return cls(kind="jira_detail", data={"issue": detail})

    @classmethod
    def jira_action(cls, action: str, data: dict[str, Any]) -> ToolResult:
        return cls(kind="jira_action", data={"action": action, **data})

    @classmethod
    def athena_query(cls, data: dict[str, Any]) -> ToolResult:
        return cls(kind="athena_query", data=data)

    @classmethod
    def cloudwatch_query(cls, data: dict[str, Any]) -> ToolResult:
        return cls(kind="cloudwatch_query", data=data)

    @classmethod
    def cloudwatch_log_groups(cls, groups: list[str], *, prefix: str = "") -> ToolResult:
        return cls(kind="cloudwatch_log_groups", data={"groups": groups, "prefix": prefix})

    @classmethod
    def grade_events_query(cls, data: dict[str, Any]) -> ToolResult:
        return cls(kind="grade_events_query", data=data)


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


def jira_summary_to_dict(issue: JiraIssueSummary) -> dict[str, Any]:
    return {
        "key": issue.key,
        "summary": issue.summary,
        "status": issue.status,
        "issue_type": issue.issue_type,
        "assignee": issue.assignee,
        "priority": issue.priority,
        "url": issue.url,
    }


def jira_summary_from_dict(data: dict[str, Any]) -> JiraIssueSummary:
    return JiraIssueSummary(
        key=str(data.get("key") or ""),
        summary=str(data.get("summary") or ""),
        status=str(data.get("status") or ""),
        issue_type=str(data.get("issue_type") or ""),
        assignee=str(data.get("assignee") or ""),
        priority=str(data.get("priority") or ""),
        url=str(data.get("url") or ""),
    )
