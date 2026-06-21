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
    def structured(cls, kind: PayloadKind, data: dict[str, Any]) -> AssistantResponse:
        return cls(payload=ResponsePayload(kind=kind, data=data))
