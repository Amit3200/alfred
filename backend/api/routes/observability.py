"""Observability API — usage summaries, timeseries, and event logs."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query

from backend.api.deps import get_manager, require_admin
from backend.config_manager import ConfigManager
from backend.observability.models import ObservabilityFilters, TimeseriesBucket
from backend.observability.pricing import build_pricing_table
from backend.observability.store import SQLiteObservabilityStore
from backend.observability.users import UserLabelEnricher

router = APIRouter(prefix="/observability", tags=["observability"])


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)


def _default_since(preset: str | None) -> datetime:
    now = datetime.now(timezone.utc)
    if preset == "24h":
        return now - timedelta(hours=24)
    if preset == "7d":
        return now - timedelta(days=7)
    if preset == "30d":
        return now - timedelta(days=30)
    if preset == "month":
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return now - timedelta(days=7)


def _filters_from_query(
    *,
    since: str | None,
    until: str | None,
    preset: str | None,
    source: str | None,
    user: str | None,
    model: str | None,
    provider: str | None,
    event_type: Literal["llm_call", "tool_call"] | None,
    tool_category: str | None,
) -> ObservabilityFilters:
    parsed_since = _parse_dt(since) or _default_since(preset)
    parsed_until = _parse_dt(until) or datetime.now(timezone.utc)
    return ObservabilityFilters(
        since=parsed_since,
        until=parsed_until,
        source=source or None,
        user_label=user or None,
        model=model or None,
        provider=provider or None,
        event_type=event_type,
        tool_category=tool_category or None,
    )


def _store(manager: ConfigManager) -> SQLiteObservabilityStore:
    return SQLiteObservabilityStore(manager.data_dir)


def _enricher(manager: ConfigManager) -> UserLabelEnricher:
    config, _ = manager.load_merged()
    return UserLabelEnricher.from_config(config, data_dir=manager.data_dir)


def _pricing_table(manager: ConfigManager):
    config, _ = manager.load_merged()
    return build_pricing_table(config.observability)


@router.get("/summary")
def usage_summary(
    manager: ConfigManager = Depends(require_admin),
    since: str | None = Query(None),
    until: str | None = Query(None),
    preset: str | None = Query("7d"),
    source: str | None = Query(None),
    user: str | None = Query(None),
    model: str | None = Query(None),
    provider: str | None = Query(None),
    event_type: Literal["llm_call", "tool_call"] | None = Query(None),
    tool_category: str | None = Query(None),
) -> dict[str, Any]:
    filters = _filters_from_query(
        since=since,
        until=until,
        preset=preset,
        source=source,
        user=user,
        model=model,
        provider=provider,
        event_type=event_type,
        tool_category=tool_category,
    )
    store = _store(manager)
    enricher = _enricher(manager)
    summary = store.summary(filters, pricing=_pricing_table(manager))
    summary.by_user = enricher.merge_by_user(summary.by_user, store.user_breakdown(filters))
    return {
        "filters": filters.model_dump(mode="json"),
        "summary": summary.model_dump(),
    }


@router.get("/timeseries")
def usage_timeseries(
    manager: ConfigManager = Depends(require_admin),
    bucket: TimeseriesBucket = Query("day"),
    since: str | None = Query(None),
    until: str | None = Query(None),
    preset: str | None = Query("7d"),
    source: str | None = Query(None),
    user: str | None = Query(None),
    model: str | None = Query(None),
    provider: str | None = Query(None),
    event_type: Literal["llm_call", "tool_call"] | None = Query(None),
    tool_category: str | None = Query(None),
) -> dict[str, Any]:
    filters = _filters_from_query(
        since=since,
        until=until,
        preset=preset,
        source=source,
        user=user,
        model=model,
        provider=provider,
        event_type=event_type,
        tool_category=tool_category,
    )
    series = _store(manager).timeseries(filters, bucket=bucket, pricing=_pricing_table(manager))
    return {
        "filters": filters.model_dump(mode="json"),
        "timeseries": series.model_dump(),
    }


@router.get("/events")
def usage_events(
    manager: ConfigManager = Depends(require_admin),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    since: str | None = Query(None),
    until: str | None = Query(None),
    preset: str | None = Query("7d"),
    source: str | None = Query(None),
    user: str | None = Query(None),
    model: str | None = Query(None),
    provider: str | None = Query(None),
    event_type: Literal["llm_call", "tool_call"] | None = Query(None),
    tool_category: str | None = Query(None),
) -> dict[str, Any]:
    filters = _filters_from_query(
        since=since,
        until=until,
        preset=preset,
        source=source,
        user=user,
        model=model,
        provider=provider,
        event_type=event_type,
        tool_category=tool_category,
    )
    page = _store(manager).list_events(filters, limit=limit, offset=offset, pricing=_pricing_table(manager))
    enricher = _enricher(manager)
    return {
        "filters": filters.model_dump(mode="json"),
        "total": page.total,
        "events": [enricher.enrich_event(event.model_dump(mode="json")) for event in page.events],
    }


@router.get("/filters")
def usage_filter_options(
    manager: ConfigManager = Depends(require_admin),
    preset: str | None = Query("30d"),
) -> dict[str, Any]:
    filters = _filters_from_query(
        since=None,
        until=None,
        preset=preset,
        source=None,
        user=None,
        model=None,
        provider=None,
        event_type=None,
        tool_category=None,
    )
    store = _store(manager)
    enricher = _enricher(manager)
    options = store.filter_options(filters)
    users = sorted(
        {
            enricher.display_name(uid, label)
            for uid, label, _count in store.user_breakdown(filters)
        }
    )
    options["users"] = users
    return options


@router.get("/checkpoints")
def get_task_checkpoints(
    task_id: str | None = Query(None),
    manager: ConfigManager = Depends(require_admin),
) -> dict[str, Any]:
    import sqlite3
    from backend.paths import db_path
    db_file = db_path(manager.data_dir)

    # Ensure database table exists
    from backend.observability.checkpoint import init_checkpoint_db
    init_checkpoint_db(db_file)

    conn = sqlite3.connect(db_file, timeout=10.0)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    if task_id:
        cursor.execute(
            """
            SELECT checkpoint, function_name, status, timestamp, error, error_stacktrace
            FROM task_checkpoints
            WHERE task_id = ?
            ORDER BY id ASC
            """,
            (task_id,),
        )
    else:
        cursor.execute(
            """
            SELECT task_id, checkpoint, function_name, status, timestamp, error, error_stacktrace
            FROM task_checkpoints
            ORDER BY id DESC
            LIMIT 100
            """
        )
    rows = cursor.fetchall()
    conn.close()

    checkpoints = [dict(r) for r in rows]
    return {"checkpoints": checkpoints}


@router.get("/health")
def observability_health(manager: ConfigManager = Depends(get_manager)) -> dict[str, str]:
    return {"status": "ok", "backend": "sqlite"}
