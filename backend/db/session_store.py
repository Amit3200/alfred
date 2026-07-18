"""SQLite-backed conversation session storage."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import DateTime, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from backend.models.response import ResponsePayload
from backend.models.session import ConversationSession, ConversationTurn
from backend.paths import db_path

logger = logging.getLogger(__name__)

MAX_TURNS = 20


class Base(DeclarativeBase):
    pass


class SessionRow(Base):
    __tablename__ = "conversation_sessions"

    key: Mapped[str] = mapped_column(String(512), primary_key=True)
    source: Mapped[str] = mapped_column(String(32), index=True)
    scope_id: Mapped[str] = mapped_column(String(128), index=True)
    thread_id: Mapped[str] = mapped_column(String(128), index=True)
    payload: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SessionStore:
    """Load/save isolated conversation sessions (Slack thread today; GitHub issue tomorrow)."""

    def __init__(self, data_dir: Path | None = None) -> None:
        path = db_path(data_dir)
        self._engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
        Base.metadata.create_all(self._engine)
        self._factory = sessionmaker(bind=self._engine, expire_on_commit=False)

    def load(self, key: str) -> ConversationSession | None:
        with self._factory() as db:
            row = db.get(SessionRow, key)
            if row is None:
                return None
            data = json.loads(row.payload)
            return ConversationSession.model_validate(data)

    def save(self, session: ConversationSession) -> None:
        session.turns = session.turns[-MAX_TURNS:]
        session.metadata["updated_at"] = datetime.now(timezone.utc).isoformat()
        payload = session.model_dump(mode="json")
        now = datetime.now(timezone.utc)
        with self._factory() as db:
            row = db.get(SessionRow, session.key)
            if row is None:
                row = SessionRow(
                    key=session.key,
                    source=session.source,
                    scope_id=session.scope_id,
                    thread_id=session.thread_id,
                    payload=json.dumps(payload),
                    updated_at=now,
                )
                db.add(row)
            else:
                row.payload = json.dumps(payload)
                row.updated_at = now
            db.commit()
        logger.debug("Saved session %s (%d turns)", session.key, len(session.turns))

    def append_exchange(
        self,
        key: str,
        *,
        source: str,
        scope_id: str,
        thread_id: str,
        user_content: str,
        assistant_content: str,
        context_snapshot: str | None = None,
        assistant_payload: ResponsePayload | None = None,
        metadata_patch: dict[str, Any] | None = None,
    ) -> ConversationSession:
        session = self.load(key) or ConversationSession(
            key=key,
            source=source,
            scope_id=scope_id,
            thread_id=thread_id,
        )
        if metadata_patch:
            session.metadata.update(metadata_patch)
        user_already_persisted = (
            session.turns
            and session.turns[-1].role == "user"
            and session.turns[-1].content == user_content
        )
        if not user_already_persisted:
            session.turns.append(ConversationTurn(role="user", content=user_content))
        session.turns.append(
            ConversationTurn(
                role="assistant",
                content=assistant_content,
                payload=assistant_payload,
            )
        )
        if context_snapshot:
            session.context_snapshot = context_snapshot
        self.save(session)
        return session

    def append_user_turn(
        self,
        key: str,
        *,
        source: str,
        scope_id: str,
        thread_id: str,
        user_content: str,
    ) -> ConversationSession:
        """Persist the user message immediately (async UI enqueue)."""
        session = self.load(key) or ConversationSession(
            key=key,
            source=source,
            scope_id=scope_id,
            thread_id=thread_id,
        )
        if (
            session.turns
            and session.turns[-1].role == "user"
            and session.turns[-1].content == user_content
        ):
            return session
        session.turns.append(ConversationTurn(role="user", content=user_content))
        self.save(session)
        return session

    def append_assistant_turn(
        self,
        key: str,
        *,
        source: str,
        scope_id: str,
        thread_id: str,
        assistant_content: str,
        assistant_payload: ResponsePayload | None = None,
        metadata_patch: dict[str, Any] | None = None,
    ) -> ConversationSession:
        session = self.load(key) or ConversationSession(
            key=key,
            source=source,
            scope_id=scope_id,
            thread_id=thread_id,
        )
        if metadata_patch:
            session.metadata.update(metadata_patch)
        session.turns.append(
            ConversationTurn(
                role="assistant",
                content=assistant_content,
                payload=assistant_payload,
            )
        )
        self.save(session)
        return session

    def delete(self, key: str) -> bool:
        with self._factory() as db:
            row = db.get(SessionRow, key)
            if row is None:
                return False
            db.delete(row)
            db.commit()
            return True

    def list_by_source(self, source: str) -> list[ConversationSession]:
        with self._factory() as db:
            stmt = (
                select(SessionRow)
                .where(SessionRow.source == source)
                .order_by(SessionRow.updated_at.desc())
            )
            rows = db.scalars(stmt).all()
            sessions: list[ConversationSession] = []
            for row in rows:
                data = json.loads(row.payload)
                sessions.append(ConversationSession.model_validate(data))
            return sessions
