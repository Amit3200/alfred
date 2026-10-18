"""Persist connector entity → Slack List / JIRA mappings."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ConnectorSyncStore:
    def __init__(self, data_dir: Path) -> None:
        self._path = data_dir / "connector_sync.json"
        self._lock = threading.Lock()

    def get(self, key: str) -> dict[str, Any] | None:
        data = self._read()
        entry = data.get(key)
        return entry if isinstance(entry, dict) else None

    def put(self, key: str, patch: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            data = self._read()
            current = dict(data.get(key) or {})
            current.update(patch)
            current["updated_at"] = datetime.now(timezone.utc).isoformat()
            if "created_at" not in current:
                current["created_at"] = current["updated_at"]
            data[key] = current
            self._write(data)
            return current

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
