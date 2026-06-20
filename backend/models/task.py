"""Normalized task model for ingress → orchestration."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field


TaskSource = Literal["slack", "cli", "git", "web", "ui"]


class Task(BaseModel):
    """Single unit of work from any ingress channel."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    source: TaskSource
    user_id: str
    channel_id: str = ""
    thread_ts: str | None = None
    raw_text: str
    cleaned_intent: str
    metadata: dict[str, Any] = Field(default_factory=dict)
