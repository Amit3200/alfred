"""Persistent registry for Slack board display IDs and ticket thread links."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class SlackBoardStore:
    """JSON store: board counters + record metadata for cross-channel lookup."""

    def __init__(self, data_dir: Path) -> None:
        self._path = data_dir / "slack_board_registry.json"
        self._data: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            self._data = {"boards": {}, "records": {}, "schema_cache": {}}
            return
        try:
            self._data = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            logger.warning("Corrupt slack_board_registry.json — resetting")
            self._data = {"boards": {}, "records": {}, "schema_cache": {}}

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")

    def next_display_id(self, board_key: str, *, prefix: str = "TS") -> str:
        from backend.db.slack_workflows_db import db_bump_display_id

        db_id = db_bump_display_id(self._path.parent, board_key, prefix=prefix)
        if db_id:
            return db_id

        boards = self._data.setdefault("boards", {})
        bucket = boards.setdefault(board_key, {"next_num": 1, "prefix": prefix})
        num = int(bucket.get("next_num") or 1)
        bucket["next_num"] = num + 1
        bucket["prefix"] = prefix
        self.save()
        return f"{prefix}-{num}"

    def register_record(
        self,
        record_id: str,
        *,
        board_key: str,
        list_id: str,
        channel_id: str,
        display_id: str = "",
        thread_ts: str = "",
        title: str = "",
    ) -> None:
        records = self._data.setdefault("records", {})
        records[record_id] = {
            "board_key": board_key,
            "list_id": list_id,
            "channel_id": channel_id,
            "display_id": display_id,
            "thread_ts": thread_ts,
            "title": title,
        }
        if display_id:
            records[display_id.upper()] = records[record_id]
        self.save()

    def find_record(self, token: str) -> dict[str, Any] | None:
        records = self._data.get("records") or {}
        key = (token or "").strip()
        if not key:
            return None
        if key in records and isinstance(records[key], dict):
            row = records[key]
            if row.get("list_id"):
                return dict(row)
        upper = key.upper()
        if upper in records and isinstance(records[upper], dict):
            row = records[upper]
            if row.get("list_id"):
                return dict(row)
        for rid, meta in records.items():
            if not rid.startswith("Rec") or not isinstance(meta, dict):
                continue
            if str(meta.get("display_id") or "").upper() == upper:
                return dict(meta)
            if str(meta.get("title") or "").lower() == key.lower():
                return dict(meta)
        return None

    def resolve_record(self, token: str) -> tuple[str, dict[str, Any]] | None:
        """Return (record_id, meta) for display id, Rec id, or title match."""
        key = (token or "").strip()
        if not key:
            return None
        records = self._data.get("records") or {}
        if key.startswith("Rec") and key in records:
            return key, dict(records[key])
        meta = self.find_record(key)
        if not meta:
            return None
        for rid, row in records.items():
            if rid.startswith("Rec") and isinstance(row, dict) and row.get("list_id") == meta.get("list_id"):
                if row.get("display_id") == meta.get("display_id") and row.get("title") == meta.get("title"):
                    return rid, dict(row)
        return None

    def get_schema_cache(self, list_id: str) -> list[dict[str, Any]] | None:
        cached = (self._data.get("schema_cache") or {}).get(list_id)
        return list(cached) if isinstance(cached, list) else None

    def set_schema_cache(self, list_id: str, schema: list[dict[str, Any]]) -> None:
        cache = self._data.setdefault("schema_cache", {})
        cache[list_id] = schema
        self.save()
