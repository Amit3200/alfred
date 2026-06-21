"""Request-scoped interaction context for observability."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import Any, Iterator

from backend.models.session import task_session_key
from backend.models.task import Task

_interaction_ctx: ContextVar["InteractionContext | None"] = ContextVar(
    "alfred_interaction_ctx",
    default=None,
)


@dataclass
class InteractionContext:
    source: str
    user_id: str = ""
    user_label: str = ""
    task_id: str | None = None
    session_key: str | None = None
    call_kind: str = "chat"
    skill_name: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def get_interaction_context() -> InteractionContext | None:
    return _interaction_ctx.get()


def context_from_task(task: Task) -> InteractionContext:
    user_label = str(task.metadata.get("user_label") or "").strip()
    if not user_label and task.source == "ui":
        user_label = "Admin UI"
    return InteractionContext(
        source=task.source,
        user_id=task.user_id,
        user_label=user_label or task.user_id,
        task_id=task.id,
        session_key=task_session_key(task),
        metadata=dict(task.metadata),
    )


@contextmanager
def interaction_scope(task: Task, *, skill_name: str | None = None) -> Iterator[InteractionContext]:
    ctx = context_from_task(task)
    if skill_name:
        ctx.skill_name = skill_name
    token = _interaction_ctx.set(ctx)
    try:
        yield ctx
    finally:
        _interaction_ctx.reset(token)


def set_call_kind(call_kind: str) -> None:
    ctx = _interaction_ctx.get()
    if ctx is not None:
        ctx.call_kind = call_kind


def set_skill_name(skill_name: str | None) -> None:
    ctx = _interaction_ctx.get()
    if ctx is not None:
        ctx.skill_name = skill_name


def bind_interaction_context(ctx: InteractionContext) -> Token:
    return _interaction_ctx.set(ctx)


def reset_interaction_context(token: Token) -> None:
    _interaction_ctx.reset(token)
