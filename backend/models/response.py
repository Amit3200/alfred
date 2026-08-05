"""Structured assistant responses — canonical JSON, rendered per channel."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

PayloadKind = Literal[
    "text",
    "pr_list",
    "pr_detail",
    "repo_list",
    "error",
    "code_grep",
    "file_content",
    "git_log",
    "git_blame",
    "git_show",
    "jira_list",
    "jira_detail",
    "jira_action",
    "athena_query",
    "cloudwatch_query",
    "cloudwatch_log_groups",
    "google_sheet",
    "google_doc",
    "web_search",
    "pr_created",
    "doc_search",
    "doc_content",
    "doc_answer",
]


class ResponsePayload(BaseModel):
    kind: PayloadKind
    data: dict[str, Any] = Field(default_factory=dict)


class AssistantResponse(BaseModel):
    """Canonical response from TaskProcessor; render at Slack/UI/CLI boundaries."""

    payload: ResponsePayload
    text: str | None = None

    @classmethod
    def from_text(cls, content: str) -> AssistantResponse:
        return cls(payload=ResponsePayload(kind="text", data={"text": content}), text=content)

    @classmethod
    def error(cls, message: str) -> AssistantResponse:
        return cls(payload=ResponsePayload(kind="error", data={"message": message}), text=message)

    @classmethod
    def structured(
        cls,
        kind: PayloadKind,
        data: dict[str, Any],
        *,
        text: str | None = None,
    ) -> AssistantResponse:
        return cls(payload=ResponsePayload(kind=kind, data=data), text=text)
