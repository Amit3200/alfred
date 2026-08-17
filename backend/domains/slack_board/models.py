"""Slack List board domain models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def _str(arguments: dict[str, Any], key: str) -> str:
    return str(arguments.get(key) or "").strip()


@dataclass(frozen=True)
class CreateTaskRequest:
    title: str
    description: str = ""
    severity: str = ""
    merchant: str = ""
    assignee_user_id: str = ""
    channel_id: str = ""
    thread_ts: str = ""

    @classmethod
    def from_args(cls, arguments: dict[str, Any], *, channel_id: str = "", thread_ts: str = "") -> CreateTaskRequest:
        return cls(
            title=_str(arguments, "title"),
            description=_str(arguments, "description"),
            severity=_str(arguments, "severity"),
            merchant=_str(arguments, "merchant"),
            assignee_user_id=_str(arguments, "assignee_user_id"),
            channel_id=channel_id or _str(arguments, "channel_id"),
            thread_ts=thread_ts or _str(arguments, "thread_ts"),
        )

    def validate(self) -> str | None:
        if not self.title:
            return "title is required."
        return None


@dataclass(frozen=True)
class UpdateTaskRequest:
    ticket_ref: str
    status: str = ""
    assignee_user_id: str = ""
    severity: str = ""
    channel_id: str = ""
    record_id_hint: str = ""

    @classmethod
    def from_args(cls, arguments: dict[str, Any], *, channel_id: str = "") -> UpdateTaskRequest:
        return cls(
            ticket_ref=_str(arguments, "ticket_ref"),
            status=_str(arguments, "status"),
            assignee_user_id=_str(arguments, "assignee_user_id"),
            severity=_str(arguments, "severity"),
            channel_id=channel_id or _str(arguments, "channel_id"),
            record_id_hint=_str(arguments, "record_id_hint"),
        )

    def validate(self) -> str | None:
        if not self.ticket_ref:
            return "ticket_ref is required."
        return None


@dataclass(frozen=True)
class SearchTasksRequest:
    query: str = ""
    status: str = ""
    limit: int = 20

    @classmethod
    def from_args(cls, arguments: dict[str, Any]) -> SearchTasksRequest:
        try:
            limit = int(arguments.get("limit") or 20)
        except (TypeError, ValueError):
            limit = 20
        return cls(
            query=_str(arguments, "query"),
            status=_str(arguments, "status"),
            limit=limit,
        )


@dataclass(frozen=True)
class CommentTaskRequest:
    ticket_ref: str
    text: str
    channel_id: str = ""
    thread_ts: str = ""

    @classmethod
    def from_args(
        cls,
        arguments: dict[str, Any],
        *,
        channel_id: str = "",
        thread_ts: str = "",
    ) -> CommentTaskRequest:
        return cls(
            ticket_ref=_str(arguments, "ticket_ref"),
            text=_str(arguments, "text"),
            channel_id=channel_id or _str(arguments, "channel_id"),
            thread_ts=thread_ts or _str(arguments, "thread_ts"),
        )

    def validate(self) -> str | None:
        if not self.ticket_ref or not self.text:
            return "ticket_ref and text are required."
        return None
