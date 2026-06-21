"""Conversation session models — isolated per ingress thread."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from backend.models.response import ResponsePayload

Role = Literal["user", "assistant"]


class ConversationTurn(BaseModel):
    role: Role
    content: str
    payload: ResponsePayload | None = None


class ConversationSession(BaseModel):
    """Persistent memory for one conversation scope (e.g. Slack thread)."""

    key: str
    source: str
    scope_id: str
    thread_id: str
    turns: list[ConversationTurn] = Field(default_factory=list)
    context_snapshot: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


def session_key_for_task(source: str, scope_id: str, thread_id: str) -> str:
    """Stable, isolated key: `{source}:{scope}:{thread}`."""
    return f"{source}:{scope_id}:{thread_id}"


def task_session_key(task: Any) -> str | None:
    """Build session key from a Task, or None if not session-backed."""
    if task.source == "ui":
        chat_id = task.metadata.get("chat_id") or task.channel_id or task.thread_ts
        if chat_id:
            return session_key_for_task("ui", str(chat_id), str(chat_id))
        return None
    if not task.channel_id or not task.thread_ts:
        return None
    return session_key_for_task(task.source, task.channel_id, task.thread_ts)


def mirror_workspace_key(task: Any) -> str:
    """Stable workspace id for repo mirrors — one checkout copy per conversation."""
    key = task_session_key(task)
    if key:
        return key
    user = getattr(task, "user_id", None) or "anonymous"
    return session_key_for_task(task.source, str(user), "ephemeral")
