"""Persist Slack List record → JIRA issue mappings to avoid duplicate creates."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ListJiraSyncStore:
    def __init__(self, data_dir: Path) -> None:
        self._path = data_dir / "list_jira_sync.json"
        self._lock = threading.Lock()

    def get(self, record_id: str) -> dict[str, Any] | None:
        data = self._read()
        entry = data.get(record_id)
        return entry if isinstance(entry, dict) else None

    def has(self, record_id: str) -> bool:
        return self.get(record_id) is not None

    def put(
        self,
        record_id: str,
        *,
        jira_key: str,
        jira_url: str,
        list_id: str = "",
        channel_id: str = "",
        thread_ts: str = "",
    ) -> None:
        with self._lock:
            data = self._read()
            data[record_id] = {
                "jira_key": jira_key,
                "jira_url": jira_url,
                "list_id": list_id,
                "channel_id": channel_id,
                "thread_ts": thread_ts,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            self._write(data)

    def _read(self) -> dict[str, Any]:
        if not self._path.exists():
            return {}
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return raw if isinstance(raw, dict) else {}

    def _write(self, data: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(data, indent=2), encoding="utf-8")
