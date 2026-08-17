"""JIRA domain service — business verbs over JiraApiClient."""

from __future__ import annotations

from typing import Any

from backend.domains.jira.models import (
    AssignIssueRequest,
    CommentRequest,
    CreateIssueRequest,
    LinkIssueRequest,
    SearchIssuesRequest,
    TransitionRequest,
    UpdateIssueRequest,
)
from backend.integrations.jira.api import JiraApiClient, JiraIssueSummary
from backend.models.config import AlfredConfig


class JiraService:
    """Create, assign, transition, comment, search — no LLM knowledge."""

    def __init__(self, client: JiraApiClient) -> None:
        self.client = client

    @classmethod
    def from_config(cls, config: AlfredConfig) -> JiraService:
        return cls(JiraApiClient.from_alfred_config(config))

    def create_issue(self, req: CreateIssueRequest) -> dict[str, Any]:
        return self.client.create_issue(
            project=req.project,
            summary=req.summary,
            issue_type=req.issue_type,
            priority=req.priority or None,
            description=req.description or None,
            reporter=req.reporter or None,
            assignee=req.assignee or None,
            resilient=True,
        )

    def assign_issue(self, req: AssignIssueRequest) -> dict[str, Any]:
        return self.client.assign_issue(req.issue_key, assignee=req.assignee)

    def transition_issue(self, req: TransitionRequest) -> dict[str, Any]:
        return self.client.transition_issue(req.issue_key, transition=req.transition)

    def add_comment(self, req: CommentRequest) -> dict[str, Any]:
        return self.client.add_comment(req.issue_key, req.comment)

    def update_issue(self, req: UpdateIssueRequest) -> dict[str, Any]:
        return self.client.update_issue(
            req.issue_key,
            summary=req.summary or None,
            description=req.description,
            append_description=not req.replace_description,
        )

    def link_remote(self, req: LinkIssueRequest) -> dict[str, Any]:
        return self.client.link_remote(
            req.issue_key,
            url=req.url,
            title=req.title or None,
        )

    def get_issue(self, issue_key: str) -> dict[str, Any]:
        return self.client.get_issue(issue_key)

    def search_issues(self, req: SearchIssuesRequest) -> list[JiraIssueSummary]:
        return self.client.search_issues(
            jql=req.jql or None,
            project=req.project or None,
            status=req.status or None,
            assignee=req.assignee or None,
            max_results=req.max_results,
        )
