"""SQLite maintenance — stats and cleanup for .alfred/alfred.db."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from sqlalchemy import create_engine, delete, func, select, text
from sqlalchemy.orm import sessionmaker

from backend.observability.store import InteractionEventRow
from backend.paths import db_path
from backend.db.session_store import SessionRow
from backend.db.slack_user_cache import SlackUserNameRow

logger = logging.getLogger(__name__)

DbCleanupScope = Literal["observability", "sessions", "slack_cache", "all"]


def _engine(data_dir: Path | None):
    path = db_path(data_dir)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    SessionRow.__table__.create(engine, checkfirst=True)
    InteractionEventRow.__table__.create(engine, checkfirst=True)
    SlackUserNameRow.__table__.create(engine, checkfirst=True)
    return engine, path


def _table_stats(db, row_cls, time_col) -> dict[str, Any]:
    count = db.scalar(select(func.count()).select_from(row_cls)) or 0
    stats: dict[str, Any] = {"rows": int(count)}
    if count and time_col is not None:
        oldest = db.scalar(select(func.min(time_col)))
        newest = db.scalar(select(func.max(time_col)))
        stats["oldest"] = oldest.isoformat() if oldest else None
        stats["newest"] = newest.isoformat() if newest else None
    return stats


def get_db_stats(data_dir: Path | None = None) -> dict[str, Any]:
    engine, path = _engine(data_dir)
    size_bytes = path.stat().st_size if path.is_file() else 0
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        tables = {
            "interaction_events": _table_stats(db, InteractionEventRow, InteractionEventRow.recorded_at),
            "conversation_sessions": _table_stats(db, SessionRow, SessionRow.updated_at),
            "slack_user_names": _table_stats(db, SlackUserNameRow, SlackUserNameRow.updated_at),
        }
    rel = None
    try:
        rel = str(path.relative_to(path.parent))
    except ValueError:
        rel = path.name
    return {
        "path": str(path),
        "rel_path": rel,
        "size_bytes": size_bytes,
        "tables": tables,
    }


def cleanup_db(
    data_dir: Path | None = None,
    *,
    scope: DbCleanupScope,
    older_than_days: int | None = None,
    vacuum: bool = True,
) -> dict[str, Any]:
    """Delete rows by scope. Optionally keep recent data with older_than_days."""
    if older_than_days is not None and older_than_days < 0:
        raise ValueError("older_than_days must be >= 0")

    cutoff: datetime | None = None
    if older_than_days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)

    engine, path = _engine(data_dir)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    removed: dict[str, int] = {
        "interaction_events": 0,
        "conversation_sessions": 0,
        "slack_user_names": 0,
    }

    scopes: set[DbCleanupScope]
    if scope == "all":
        scopes = {"observability", "sessions", "slack_cache"}
    else:
        scopes = {scope}

    with factory() as db:
        if "observability" in scopes:
            stmt = delete(InteractionEventRow)
            if cutoff is not None:
                stmt = stmt.where(InteractionEventRow.recorded_at < cutoff)
            result = db.execute(stmt)
            removed["interaction_events"] = int(result.rowcount or 0)

        if "sessions" in scopes:
            stmt = delete(SessionRow)
            if cutoff is not None:
                stmt = stmt.where(SessionRow.updated_at < cutoff)
            result = db.execute(stmt)
            removed["conversation_sessions"] = int(result.rowcount or 0)

        if "slack_cache" in scopes:
            stmt = delete(SlackUserNameRow)
            if cutoff is not None:
                stmt = stmt.where(SlackUserNameRow.updated_at < cutoff)
            result = db.execute(stmt)
            removed["slack_user_names"] = int(result.rowcount or 0)

        db.commit()

    if vacuum:
        with engine.connect() as conn:
            conn.execute(text("VACUUM"))
            conn.commit()

    stats = get_db_stats(data_dir)
    logger.info(
        "DB cleanup scope=%s older_than_days=%s removed=%s size_bytes=%s",
        scope,
        older_than_days,
        removed,
        stats.get("size_bytes"),
    )
    return {
        "ok": True,
        "scope": scope,
        "older_than_days": older_than_days,
        "removed": removed,
        "stats": stats,
    }
