"""Observability event models."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

EventType = Literal["llm_call", "tool_call"]
InteractionSource = Literal["slack", "ui", "cli", "git", "jira", "web"]
ToolCategory = Literal["git", "slack", "jira", "ui", "aws", "other"]
TimeseriesBucket = Literal["hour", "day", "month"]


class InteractionEvent(BaseModel):
    """Single recorded AI or tool interaction."""

    recorded_at: datetime
    event_type: EventType
    source: str
    user_id: str = ""
    user_label: str = ""
    task_id: str | None = None
    session_key: str | None = None
    provider: str | None = None
    model: str | None = None
    call_kind: str = "chat"
    skill_name: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    duration_ms: int | None = None
    tool_name: str | None = None
    tool_category: str | None = None
    success: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class ObservabilityFilters(BaseModel):
    since: datetime | None = None
    until: datetime | None = None
    source: str | None = None
    user_id: str | None = None
    user_label: str | None = None
    model: str | None = None
    provider: str | None = None
    event_type: EventType | None = None
    tool_category: str | None = None
    call_kind: str | None = None


class UsageSummary(BaseModel):
    llm_calls: int = 0
    tool_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    by_source: dict[str, int] = Field(default_factory=dict)
    by_user: dict[str, int] = Field(default_factory=dict)
    by_model: dict[str, int] = Field(default_factory=dict)
    by_tool_category: dict[str, int] = Field(default_factory=dict)


class TimeseriesPoint(BaseModel):
    period: str
    llm_calls: int = 0
    tool_calls: int = 0
    total_tokens: int = 0


class TimeseriesResponse(BaseModel):
    bucket: TimeseriesBucket
    points: list[TimeseriesPoint] = Field(default_factory=list)


class EventsPage(BaseModel):
    total: int
    events: list[InteractionEvent] = Field(default_factory=list)
