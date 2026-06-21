"""Persistent cache of Slack user ID → display name."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import DateTime, String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from backend.paths import db_path

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


class SlackUserNameRow(Base):
    __tablename__ = "slack_user_names"

    user_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(256))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SlackUserCache:
    def __init__(self, data_dir: Path | None = None) -> None:
        path = db_path(data_dir)
        self._engine = create_engine(
            f"sqlite:///{path}",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(self._engine)
        self._factory = sessionmaker(bind=self._engine, expire_on_commit=False)

    def get(self, user_id: str) -> str | None:
        with self._factory() as db:
            row = db.get(SlackUserNameRow, user_id)
            if row is None:
                return None
            return row.display_name

    def get_many(self) -> dict[str, str]:
        with self._factory() as db:
            rows = db.scalars(select(SlackUserNameRow)).all()
            return {row.user_id: row.display_name for row in rows}

    def remember(self, user_id: str, display_name: str) -> None:
        user_id = user_id.strip()
        display_name = display_name.strip()
        if not user_id or not display_name or display_name == user_id:
            return
        now = datetime.now(timezone.utc)
        with self._factory() as db:
            row = db.get(SlackUserNameRow, user_id)
            if row is None:
                db.add(
                    SlackUserNameRow(
                        user_id=user_id,
                        display_name=display_name,
                        updated_at=now,
                    )
                )
            else:
                row.display_name = display_name
                row.updated_at = now
            db.commit()

    def remember_many(self, mapping: dict[str, str]) -> None:
        for user_id, display_name in mapping.items():
            self.remember(user_id, display_name)
