"""Build safe Athena SQL for a configured grade_events table."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from backend.aws.athena import AthenaClient
from backend.models.config import AlfredConfig

DEFAULT_LIMIT = 200
FULL_DATA_MAX_LIMIT = 5000

GRADE_EVENTS_COLUMNS = (
    "_id",
    "__v",
    "created_at",
    "updated_at",
    "sent_at",
    "team",
    "timestamp",
    "category",
    "kind",
    "platform",
    "merchant_id",
    "environment",
    "fp_id",
    "client_ip",
    "user_agent",
    "session_id",
    "source",
    "data",
    "error",
)


@dataclass
class GradeEventsFilters:
    kind: str | None = None
    merchant_id: str | None = None
    session_id: str | None = None
    fp_id: str | None = None
    environment: str | None = None
    category: str | None = None
    platform: str | None = None
    date: str | None = None
    date_from: str | None = None
    date_to: str | None = None
    hour: str | None = None
    errors_only: bool = False


def _sql_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _normalize_hour(value: str) -> str:
    text = value.strip()
    if text.isdigit():
        return text.zfill(2)
    return text


def _has_entity_filters(filters: GradeEventsFilters) -> bool:
    return bool(
        filters.kind
        or filters.merchant_id
        or filters.session_id
        or filters.fp_id
        or filters.environment
        or filters.category
        or filters.platform
    )


def _has_date_context(filters: GradeEventsFilters) -> bool:
    return bool(filters.date or filters.date_from or filters.date_to or filters.hour)


def _partition_window_hours(hours: int, *, now: datetime | None = None) -> str:
    anchor = now or datetime.now(UTC)
    start = anchor - timedelta(hours=hours)
    start = start.replace(minute=0, second=0, microsecond=0)
    end = anchor.replace(minute=0, second=0, microsecond=0)

    clauses: list[str] = []
    cursor = start
    while cursor <= end:
        date_value = cursor.strftime("%Y-%m-%d")
        hour_value = cursor.strftime("%H")
        clauses.append(f"(date = {_sql_string(date_value)} AND hour = {_sql_string(hour_value)})")
        cursor += timedelta(hours=1)

    if not clauses:
        date_value = anchor.strftime("%Y-%m-%d")
        hour_value = anchor.strftime("%H")
        return f"(date = {_sql_string(date_value)} AND hour = {_sql_string(hour_value)})"
    if len(clauses) == 1:
        return clauses[0]
    return "(" + " OR ".join(clauses) + ")"


def _partition_window_days(days: int, *, now: datetime | None = None) -> str:
    anchor = (now or datetime.now(UTC)).date()
    start = anchor - timedelta(days=max(days - 1, 0))
    start_value = start.isoformat()
    end_value = anchor.isoformat()
    if start_value == end_value:
        return f"date = {_sql_string(end_value)}"
    return f"date >= {_sql_string(start_value)} AND date <= {_sql_string(end_value)}"


def build_grade_events_sql(
    config: AlfredConfig,
    filters: GradeEventsFilters,
    *,
    full_data: bool = False,
    limit: int = DEFAULT_LIMIT,
    select_columns: list[str] | None = None,
    now: datetime | None = None,
) -> tuple[str, dict[str, Any]]:
    """Return SQL and metadata describing guardrails applied."""
    table = (config.aws.grade_events_table or "grade_events").strip()
    database = (config.aws.grade_events_database or config.aws.athena_database or "").strip()
    if not database:
        raise ValueError(
            "Athena database is required. Set aws.grade_events_database or aws.athena_database."
        )

    columns = select_columns or [
        "timestamp",
        "date",
        "hour",
        "kind",
        "category",
        "merchant_id",
        "session_id",
        "fp_id",
        "environment",
        "platform",
        "source",
        "error",
        "data",
    ]
    unknown = [col for col in columns if col not in GRADE_EVENTS_COLUMNS and col not in {"date", "hour"}]
    if unknown:
        raise ValueError(f"Unknown grade_events columns: {', '.join(unknown)}")

    where_parts: list[str] = []
    guardrails: dict[str, Any] = {
        "table": table,
        "database": database,
        "default_limit": DEFAULT_LIMIT,
    }

    if filters.date:
        where_parts.append(f"date = {_sql_string(filters.date.strip())}")
    else:
        if filters.date_from:
            where_parts.append(f"date >= {_sql_string(filters.date_from.strip())}")
        if filters.date_to:
            where_parts.append(f"date <= {_sql_string(filters.date_to.strip())}")

    if filters.hour:
        where_parts.append(f"hour = {_sql_string(_normalize_hour(filters.hour))}")

    if not _has_date_context(filters):
        if _has_entity_filters(filters):
            where_parts.append(_partition_window_days(1, now=now))
            guardrails["time_window"] = "last_1_day"
            guardrails["time_window_reason"] = "entity filters without explicit date"
        else:
            where_parts.append(_partition_window_hours(2, now=now))
            guardrails["time_window"] = "last_2_hours"
            guardrails["time_window_reason"] = "no filters or date provided"

    if filters.kind:
        where_parts.append(f"kind = {_sql_string(filters.kind.strip())}")
    if filters.merchant_id:
        where_parts.append(f"merchant_id = {_sql_string(filters.merchant_id.strip())}")
    if filters.session_id:
        where_parts.append(f"session_id = {_sql_string(filters.session_id.strip())}")
    if filters.fp_id:
        where_parts.append(f"fp_id = {_sql_string(filters.fp_id.strip())}")
    if filters.environment:
        where_parts.append(f"environment = {_sql_string(filters.environment.strip())}")
    if filters.category:
        where_parts.append(f"category = {_sql_string(filters.category.strip())}")
    if filters.platform:
        where_parts.append(f"platform = {_sql_string(filters.platform.strip())}")
    if filters.errors_only:
        where_parts.append("(error IS NOT NULL AND error != '')")

    selected = ", ".join(columns)
    sql = f"SELECT {selected} FROM {database}.{table}"
    if where_parts:
        sql += "\nWHERE " + "\n  AND ".join(where_parts)
    sql += "\nORDER BY timestamp DESC"

    if full_data:
        applied_limit = min(max(int(limit or FULL_DATA_MAX_LIMIT), 1), FULL_DATA_MAX_LIMIT)
        sql += f"\nLIMIT {applied_limit}"
        guardrails["limit"] = applied_limit
        guardrails["full_data"] = True
    else:
        applied_limit = min(max(int(limit or DEFAULT_LIMIT), 1), DEFAULT_LIMIT)
        sql += f"\nLIMIT {applied_limit}"
        guardrails["limit"] = applied_limit
        guardrails["full_data"] = False

    guardrails["sql"] = sql
    return sql, guardrails


class GradeEventsClient:
    def __init__(self, config: AlfredConfig) -> None:
        self._config = config
        self._athena = AthenaClient.from_config(config)

    @classmethod
    def from_config(cls, config: AlfredConfig) -> GradeEventsClient:
        if not config.aws.enabled:
            raise RuntimeError("AWS integration is disabled.")
        return cls(config)

    def query(
        self,
        *,
        kind: str | None = None,
        merchant_id: str | None = None,
        session_id: str | None = None,
        fp_id: str | None = None,
        environment: str | None = None,
        category: str | None = None,
        platform: str | None = None,
        date: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        hour: str | None = None,
        errors_only: bool = False,
        full_data: bool = False,
        limit: int = DEFAULT_LIMIT,
        max_wait_seconds: int = 120,
    ) -> dict[str, Any]:
        filters = GradeEventsFilters(
            kind=kind,
            merchant_id=merchant_id,
            session_id=session_id,
            fp_id=fp_id,
            environment=environment,
            category=category,
            platform=platform,
            date=date,
            date_from=date_from,
            date_to=date_to,
            hour=hour,
            errors_only=errors_only,
        )
        sql, guardrails = build_grade_events_sql(
            self._config,
            filters,
            full_data=full_data,
            limit=limit,
        )
        database = guardrails["database"]
        result = self._athena.run_query(
            sql,
            database=database,
            max_wait_seconds=max_wait_seconds,
        )
        result["guardrails"] = guardrails
        result["table"] = guardrails["table"]
        return result
