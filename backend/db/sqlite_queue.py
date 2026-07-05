"""SQLite-backed persistent and crash-safe queue."""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any

from backend.abstractions import BaseQueue
from backend.paths import db_path

logger = logging.getLogger(__name__)


class SQLiteQueue(BaseQueue):
    """SQLite-backed queue implementing BaseQueue with atomic status updates."""

    def __init__(self, data_dir: Path | None = None) -> None:
        self.db_file = db_path(data_dir)
        self._init_db()

    def _init_db(self) -> None:
        conn = sqlite3.connect(self.db_file, timeout=10.0)
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS task_queue (
                id TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
            """
        )
        conn.commit()
        conn.close()

    def push(self, task: dict[str, Any]) -> str:
        task_id = task.get("id") or f"task_{int(time.time() * 1000)}"
        now = time.time()
        conn = sqlite3.connect(self.db_file, timeout=10.0)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO task_queue (id, payload, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (task_id, json.dumps(task), "pending", now, now),
        )
        conn.commit()
        conn.close()
        logger.debug("Enqueued task %s", task_id)
        return task_id

    def pop(self) -> dict[str, Any] | None:
        conn = sqlite3.connect(self.db_file, timeout=10.0)
        cursor = conn.cursor()
        # Find oldest pending task
        cursor.execute(
            "SELECT id, payload FROM task_queue WHERE status = 'pending' ORDER BY created_at ASC LIMIT 1"
        )
        row = cursor.fetchone()
        if not row:
            conn.close()
            return None

        task_id, payload = row
        now = time.time()
        # Atomically update status to running
        cursor.execute(
            "UPDATE task_queue SET status = 'running', updated_at = ? WHERE id = ?",
            (now, task_id),
        )
        conn.commit()
        conn.close()
        logger.debug("Popped/Locking task %s for execution", task_id)
        return json.loads(payload)

    def ack(self, task_id: str) -> None:
        now = time.time()
        conn = sqlite3.connect(self.db_file, timeout=10.0)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE task_queue SET status = 'completed', updated_at = ? WHERE id = ?",
            (now, task_id),
        )
        conn.commit()
        conn.close()
        logger.debug("Acknowledged task %s", task_id)

    def fail(self, task_id: str) -> None:
        now = time.time()
        conn = sqlite3.connect(self.db_file, timeout=10.0)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE task_queue SET status = 'failed', updated_at = ? WHERE id = ?",
            (now, task_id),
        )
        conn.commit()
        conn.close()
        logger.debug("Failed task %s", task_id)

    def get_status(self, task_id: str) -> str | None:
        conn = sqlite3.connect(self.db_file, timeout=10.0)
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM task_queue WHERE id = ?", (task_id,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None
