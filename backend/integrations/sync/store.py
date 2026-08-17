"""Persistent sync timestamps and metadata for integration caches."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.paths import get_data_dir


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return None


class SyncStateStore:
    """Read/write `.alfred/sync_state.json`."""

    def __init__(self, data_dir: Path | None = None) -> None:
        root = get_data_dir(data_dir)
        self._path = root / "sync_state.json"
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> dict[str, Any]:
        if not self._path.is_file():
            return {}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def save(self, data: dict[str, Any]) -> None:
        self._path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

    def get(self, key: str) -> dict[str, Any]:
        section = self.load().get(key)
        return dict(section) if isinstance(section, dict) else {}

    def update(self, key: str, patch: dict[str, Any]) -> dict[str, Any]:
        data = self.load()
        current = dict(data.get(key) or {})
        current.update(patch)
        current["last_sync_at"] = _utc_now().isoformat()
        data[key] = current
        self.save(data)
        return current

    def last_sync_at(self, key: str) -> datetime | None:
        return _parse_ts(self.get(key).get("last_sync_at"))

    def is_stale(self, key: str, *, hours: float) -> bool:
        last = self.last_sync_at(key)
        if last is None:
            return True
        age_hours = (_utc_now() - last).total_seconds() / 3600.0
        return age_hours >= max(hours, 0.01)

    def status(self) -> dict[str, Any]:
        data = self.load()
        out: dict[str, Any] = {}
        for key, section in data.items():
            if isinstance(section, dict):
                out[key] = dict(section)
        return out
