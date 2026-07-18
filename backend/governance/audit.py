"""SQLite audit log for tool invocations (governance + compliance)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import DateTime, Integer, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from backend.paths import db_path

logger = logging.getLogger(__name__)

_audit_store: "AuditStore | None" = None


class Base(DeclarativeBase):
    pass


class AuditLogRow(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    task_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    session_key: Mapped[str] = mapped_column(String(512), default="", index=True)
    source: Mapped[str] = mapped_column(String(32), default="", index=True)
    user_id: Mapped[str] = mapped_column(String(128), default="", index=True)
    channel_id: Mapped[str] = mapped_column(String(128), default="", index=True)
    skill_name: Mapped[str] = mapped_column(String(128), default="", index=True)
    tool_name: Mapped[str] = mapped_column(String(128), index=True)
    tool_args: Mapped[str] = mapped_column(Text, default="")
    result_kind: Mapped[str] = mapped_column(String(64), default="")
    success: Mapped[int] = mapped_column(Integer, default=1)
    message: Mapped[str] = mapped_column(Text, default="")
    blocked: Mapped[int] = mapped_column(Integer, default=0)


class AuditStore:
    def __init__(self, data_dir: Path | None = None) -> None:
        path = db_path(data_dir)
        self._engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
        Base.metadata.create_all(self._engine)
        self._factory = sessionmaker(bind=self._engine, expire_on_commit=False)

    def log(
        self,
        entry: dict[str, Any],
        *,
        data_dir: Path | None = None,
    ) -> None:
        del data_dir  # store is bound to engine path
        row = AuditLogRow(
            recorded_at=datetime.now(timezone.utc),
            task_id=str(entry.get("task_id") or ""),
            session_key=str(entry.get("session_key") or ""),
            source=str(entry.get("source") or ""),
            user_id=str(entry.get("user_id") or ""),
            channel_id=str(entry.get("channel_id") or ""),
            skill_name=str(entry.get("skill_name") or ""),
            tool_name=str(entry.get("tool_name") or ""),
            tool_args=json.dumps(entry.get("tool_args") or {}, default=str)[:8000],
            result_kind=str(entry.get("result_kind") or ""),
            success=1 if entry.get("success", True) else 0,
            message=str(entry.get("message") or "")[:4000],
            blocked=1 if entry.get("blocked") else 0,
        )
        try:
            with self._factory() as db:
                db.add(row)
                db.commit()
        except Exception:
            logger.exception("Failed to write audit log entry")

    def list_recent(
        self,
        *,
        limit: int = 100,
        tool_name: str | None = None,
        blocked_only: bool = False,
    ) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 500))
        with self._factory() as db:
            stmt = select(AuditLogRow).order_by(AuditLogRow.recorded_at.desc()).limit(limit)
            if tool_name:
                stmt = stmt.where(AuditLogRow.tool_name == tool_name)
            if blocked_only:
                stmt = stmt.where(AuditLogRow.blocked == 1)
            rows = db.scalars(stmt).all()
        return [
            {
                "id": row.id,
                "recorded_at": row.recorded_at.isoformat() if row.recorded_at else "",
                "task_id": row.task_id,
                "session_key": row.session_key,
                "source": row.source,
                "user_id": row.user_id,
                "channel_id": row.channel_id,
                "skill_name": row.skill_name,
                "tool_name": row.tool_name,
                "tool_args": row.tool_args,
                "result_kind": row.result_kind,
                "success": bool(row.success),
                "message": row.message,
                "blocked": bool(row.blocked),
            }
            for row in rows
        ]


def get_audit_store(data_dir: Path | None = None) -> AuditStore:
    global _audit_store
    path = db_path(data_dir)
    if _audit_store is None or str(getattr(_audit_store, "_db_path", "")) != str(path):
        store = AuditStore(data_dir)
        store._db_path = str(path)  # type: ignore[attr-defined]
        _audit_store = store
    return _audit_store
