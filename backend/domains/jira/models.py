"""JIRA domain models — request objects for service operations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def _str(arguments: dict[str, Any], key: str) -> str:
    return str(arguments.get(key) or "").strip()


@dataclass(frozen=True)
class CreateIssueRequest:
    project: str
    summary: str
    issue_type: str
    priority: str = ""
    description: str = ""
    reporter: str = ""
    assignee: str = ""

    @classmethod
    def from_args(cls, arguments: dict[str, Any]) -> CreateIssueRequest:
        return cls(
            project=_str(arguments, "project"),
            summary=_str(arguments, "summary"),
            issue_type=_str(arguments, "issue_type"),
            priority=_str(arguments, "priority"),
            description=_str(arguments, "description"),
            reporter=_str(arguments, "reporter"),
            assignee=_str(arguments, "assignee"),
        )

    def validate(self) -> str | None:
        if not self.project or not self.summary or not self.issue_type:
            return "project, summary, and issue_type are required."
        return None


@dataclass(frozen=True)
class AssignIssueRequest:
    issue_key: str
    assignee: str

    @classmethod
    def from_args(cls, arguments: dict[str, Any]) -> AssignIssueRequest:
        return cls(issue_key=_str(arguments, "issue_key"), assignee=_str(arguments, "assignee"))

    def validate(self) -> str | None:
        if not self.issue_key or not self.assignee:
            return "issue_key and assignee are required."
        return None


@dataclass(frozen=True)
class TransitionRequest:
    issue_key: str
    transition: str

    @classmethod
    def from_args(cls, arguments: dict[str, Any]) -> TransitionRequest:
        return cls(issue_key=_str(arguments, "issue_key"), transition=_str(arguments, "transition"))

    def validate(self) -> str | None:
        if not self.issue_key or not self.transition:
            return "issue_key and transition are required."
        return None


@dataclass(frozen=True)
class CommentRequest:
    issue_key: str
    comment: str

    @classmethod
    def from_args(cls, arguments: dict[str, Any]) -> CommentRequest:
        return cls(issue_key=_str(arguments, "issue_key"), comment=_str(arguments, "comment"))

    def validate(self) -> str | None:
        if not self.issue_key or not self.comment:
            return "issue_key and comment are required."
        return None


@dataclass(frozen=True)
class UpdateIssueRequest:
    issue_key: str
    summary: str = ""
    description: str | None = None
    replace_description: bool = False

    @classmethod
    def from_args(cls, arguments: dict[str, Any]) -> UpdateIssueRequest:
        description = arguments.get("description")
        desc_text = str(description).strip() if description is not None else None
        return cls(
            issue_key=_str(arguments, "issue_key"),
            summary=_str(arguments, "summary"),
            description=desc_text,
            replace_description=bool(arguments.get("replace_description")),
        )

    def validate(self) -> str | None:
        if not self.issue_key:
            return "issue_key is required."
        if not self.summary and self.description is None:
            return "At least one of summary or description is required."
        return None


@dataclass(frozen=True)
class LinkIssueRequest:
    issue_key: str
    url: str
    title: str = ""

    @classmethod
    def from_args(cls, arguments: dict[str, Any]) -> LinkIssueRequest:
        return cls(
            issue_key=_str(arguments, "issue_key"),
            url=_str(arguments, "url"),
            title=_str(arguments, "title"),
        )

    def validate(self) -> str | None:
        if not self.issue_key or not self.url:
            return "issue_key and url are required."
        return None


@dataclass(frozen=True)
class SearchIssuesRequest:
    jql: str = ""
    project: str = ""
    status: str = ""
    assignee: str = ""
    max_results: int = 25

    @classmethod
    def from_args(cls, arguments: dict[str, Any]) -> SearchIssuesRequest:
        try:
            max_results = int(arguments.get("max_results") or 25)
        except (TypeError, ValueError):
            max_results = 25
        return cls(
            jql=_str(arguments, "jql"),
            project=_str(arguments, "project"),
            status=_str(arguments, "status"),
            assignee=_str(arguments, "assignee"),
            max_results=max_results,
        )
