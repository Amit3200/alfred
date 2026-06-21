"""Observability storage — SQLite today, swappable backend later."""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import DateTime, Integer, String, Text, create_engine, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from backend.observability.models import (
    EventsPage,
    InteractionEvent,
    ObservabilityFilters,
    TimeseriesBucket,
    TimeseriesPoint,
    TimeseriesResponse,
    UsageSummary,
)
from backend.paths import db_path

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


class InteractionEventRow(Base):
    __tablename__ = "interaction_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    event_type: Mapped[str] = mapped_column(String(32), index=True)
    source: Mapped[str] = mapped_column(String(32), index=True)
    user_id: Mapped[str] = mapped_column(String(128), default="", index=True)
    user_label: Mapped[str] = mapped_column(String(256), default="", index=True)
    task_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    session_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    call_kind: Mapped[str] = mapped_column(String(64), default="chat")
    skill_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tool_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tool_category: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    success: Mapped[int] = mapped_column(Integer, default=1)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class ObservabilityStore(ABC):
    """Abstract observability backend — implement for Postgres, etc."""

    @abstractmethod
    def record(self, event: InteractionEvent) -> None: ...

    @abstractmethod
    def summary(self, filters: ObservabilityFilters) -> UsageSummary: ...

    @abstractmethod
    def timeseries(
        self,
        filters: ObservabilityFilters,
        *,
        bucket: TimeseriesBucket,
    ) -> TimeseriesResponse: ...

    @abstractmethod
    def list_events(
        self,
        filters: ObservabilityFilters,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> EventsPage: ...

    @abstractmethod
    def filter_options(self, filters: ObservabilityFilters) -> dict[str, list[str]]: ...

    @abstractmethod
    def user_breakdown(self, filters: ObservabilityFilters) -> list[tuple[str, str, int]]: ...


class SQLiteObservabilityStore(ObservabilityStore):
    def __init__(self, data_dir: Path | None = None) -> None:
        path = db_path(data_dir)
        self._engine = create_engine(
            f"sqlite:///{path}",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(self._engine)
        self._factory = sessionmaker(bind=self._engine, expire_on_commit=False)

    def record(self, event: InteractionEvent) -> None:
        row = _event_to_row(event)
        with self._factory() as db:
            db.add(row)
            db.commit()

    def summary(self, filters: ObservabilityFilters) -> UsageSummary:
        with self._factory() as db:
            rows = db.scalars(select(InteractionEventRow).where(*_where(filters))).all()

        summary = UsageSummary()
        for row in rows:
            if row.event_type == "llm_call":
                summary.llm_calls += 1
                summary.prompt_tokens += int(row.prompt_tokens or 0)
                summary.completion_tokens += int(row.completion_tokens or 0)
                summary.total_tokens += int(row.total_tokens or 0)
                if row.model:
                    summary.by_model[row.model] = summary.by_model.get(row.model, 0) + 1
            elif row.event_type == "tool_call":
                summary.tool_calls += 1
                category = row.tool_category or "other"
                summary.by_tool_category[category] = (
                    summary.by_tool_category.get(category, 0) + 1
                )

            summary.by_source[row.source] = summary.by_source.get(row.source, 0) + 1
            label = row.user_label or row.user_id or "unknown"
            summary.by_user[label] = summary.by_user.get(label, 0) + 1

        return summary

    def timeseries(
        self,
        filters: ObservabilityFilters,
        *,
        bucket: TimeseriesBucket,
    ) -> TimeseriesResponse:
        with self._factory() as db:
            rows = db.scalars(
                select(InteractionEventRow)
                .where(*_where(filters))
                .order_by(InteractionEventRow.recorded_at.asc())
            ).all()

        buckets: dict[str, TimeseriesPoint] = {}
        for row in rows:
            period = _bucket_key(row.recorded_at, bucket)
            point = buckets.setdefault(period, TimeseriesPoint(period=period))
            if row.event_type == "llm_call":
                point.llm_calls += 1
                point.total_tokens += int(row.total_tokens or 0)
            elif row.event_type == "tool_call":
                point.tool_calls += 1

        return TimeseriesResponse(
            bucket=bucket,
            points=sorted(buckets.values(), key=lambda p: p.period),
        )

    def list_events(
        self,
        filters: ObservabilityFilters,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> EventsPage:
        with self._factory() as db:
            where = _where(filters)
            total = db.scalar(
                select(func.count()).select_from(InteractionEventRow).where(*where)
            )
            rows = db.scalars(
                select(InteractionEventRow)
                .where(*where)
                .order_by(InteractionEventRow.recorded_at.desc())
                .offset(offset)
                .limit(limit)
            ).all()
        return EventsPage(total=int(total or 0), events=[_row_to_event(row) for row in rows])

    def filter_options(self, filters: ObservabilityFilters) -> dict[str, list[str]]:
        with self._factory() as db:
            rows = db.scalars(select(InteractionEventRow).where(*_where(filters))).all()

        sources: set[str] = set()
        users: set[str] = set()
        models: set[str] = set()
        providers: set[str] = set()
        categories: set[str] = set()
        for row in rows:
            sources.add(row.source)
            users.add(row.user_label or row.user_id or "unknown")
            if row.model:
                models.add(row.model)
            if row.provider:
                providers.add(row.provider)
            if row.tool_category:
                categories.add(row.tool_category)

        return {
            "sources": sorted(sources),
            "users": sorted(users),
            "models": sorted(models),
            "providers": sorted(providers),
            "tool_categories": sorted(categories),
        }

    def user_breakdown(self, filters: ObservabilityFilters) -> list[tuple[str, str, int]]:
        with self._factory() as db:
            rows = db.scalars(select(InteractionEventRow).where(*_where(filters))).all()

        counts: dict[tuple[str, str], int] = {}
        for row in rows:
            key = (row.user_id or "", row.user_label or "")
            counts[key] = counts.get(key, 0) + 1
        return [(uid, label, count) for (uid, label), count in counts.items()]


def _where(filters: ObservabilityFilters) -> list[Any]:
    clauses: list[Any] = []
    if filters.since is not None:
        clauses.append(InteractionEventRow.recorded_at >= filters.since)
    if filters.until is not None:
        clauses.append(InteractionEventRow.recorded_at <= filters.until)
    if filters.source:
        clauses.append(InteractionEventRow.source == filters.source)
    if filters.user_id:
        clauses.append(InteractionEventRow.user_id == filters.user_id)
    if filters.user_label:
        clauses.append(InteractionEventRow.user_label == filters.user_label)
    if filters.model:
        clauses.append(InteractionEventRow.model == filters.model)
    if filters.provider:
        clauses.append(InteractionEventRow.provider == filters.provider)
    if filters.event_type:
        clauses.append(InteractionEventRow.event_type == filters.event_type)
    if filters.tool_category:
        clauses.append(InteractionEventRow.tool_category == filters.tool_category)
    if filters.call_kind:
        clauses.append(InteractionEventRow.call_kind == filters.call_kind)
    return clauses


def _bucket_key(recorded_at: datetime, bucket: TimeseriesBucket) -> str:
    dt = recorded_at.astimezone(timezone.utc)
    if bucket == "hour":
        return dt.strftime("%Y-%m-%dT%H:00")
    if bucket == "day":
        return dt.strftime("%Y-%m-%d")
    return dt.strftime("%Y-%m")


def _event_to_row(event: InteractionEvent) -> InteractionEventRow:
    recorded_at = event.recorded_at
    if recorded_at.tzinfo is None:
        recorded_at = recorded_at.replace(tzinfo=timezone.utc)
    return InteractionEventRow(
        recorded_at=recorded_at,
        event_type=event.event_type,
        source=event.source,
        user_id=event.user_id,
        user_label=event.user_label,
        task_id=event.task_id,
        session_key=event.session_key,
        provider=event.provider,
        model=event.model,
        call_kind=event.call_kind,
        skill_name=event.skill_name,
        prompt_tokens=event.prompt_tokens,
        completion_tokens=event.completion_tokens,
        total_tokens=event.total_tokens,
        duration_ms=event.duration_ms,
        tool_name=event.tool_name,
        tool_category=event.tool_category,
        success=1 if event.success else 0,
        metadata_json=json.dumps(event.metadata) if event.metadata else None,
    )


def _row_to_event(row: InteractionEventRow) -> InteractionEvent:
    metadata: dict[str, Any] = {}
    if row.metadata_json:
        try:
            metadata = json.loads(row.metadata_json)
        except json.JSONDecodeError:
            logger.debug("Invalid metadata_json for event %s", row.id)
    return InteractionEvent(
        recorded_at=row.recorded_at,
        event_type=row.event_type,  # type: ignore[arg-type]
        source=row.source,
        user_id=row.user_id,
        user_label=row.user_label,
        task_id=row.task_id,
        session_key=row.session_key,
        provider=row.provider,
        model=row.model,
        call_kind=row.call_kind,
        skill_name=row.skill_name,
        prompt_tokens=row.prompt_tokens,
        completion_tokens=row.completion_tokens,
        total_tokens=row.total_tokens,
        duration_ms=row.duration_ms,
        tool_name=row.tool_name,
        tool_category=row.tool_category,
        success=bool(row.success),
        metadata=metadata,
    )
