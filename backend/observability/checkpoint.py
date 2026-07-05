"""Checkpoint-based logging helper for Alfred requests and tool executions."""

from __future__ import annotations

import contextvars
import json
import logging
import sqlite3
import time
import traceback
from pathlib import Path
from typing import Any

from backend.paths import db_path

logger = logging.getLogger(__name__)

# Context variables for request-scoped tracking
current_task_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("current_task_id", default=None)
current_data_dir: contextvars.ContextVar[Path | None] = contextvars.ContextVar("current_data_dir", default=None)


def init_checkpoint_db(db_file: Path) -> None:
    """Ensure the task_checkpoints table exists in the database."""
    conn = sqlite3.connect(db_file, timeout=10.0)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS task_checkpoints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            checkpoint TEXT NOT NULL,
            function_name TEXT NOT NULL,
            status TEXT NOT NULL,
            timestamp REAL NOT NULL,
            error TEXT,
            error_stacktrace TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def log_checkpoint(
    checkpoint: str,
    function_name: str,
    status: str,
    error: Exception | None = None,
) -> None:
    """Print a structured JSON line and log to the task_checkpoints DB table."""
    now = time.time()
    payload: dict[str, Any] = {
        "checkpoint": checkpoint,
        "function_name": function_name,
        "status": status,
        "timestamp": now,
    }
    error_name = None
    tb = None
    if error is not None:
        error_name = type(error).__name__
        payload["error"] = error_name
        tb = "".join(traceback.format_exception(type(error), error, error.__traceback__))
        payload["error_stacktrace"] = tb

    # Print JSON line to standard output
    print(json.dumps(payload), flush=True)

    # Save to SQLite if request context is active
    task_id = current_task_id.get()
    data_dir = current_data_dir.get()
    if task_id and data_dir:
        try:
            db_file = db_path(data_dir)
            init_checkpoint_db(db_file)
            conn = sqlite3.connect(db_file, timeout=10.0)
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO task_checkpoints (task_id, checkpoint, function_name, status, timestamp, error, error_stacktrace)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (task_id, checkpoint, function_name, status, now, error_name, tb),
            )
            conn.commit()
            conn.close()
        except Exception:
            logger.exception("Failed to write checkpoint log to database")


def init_feedback_db(db_file: Path) -> None:
    """Ensure the task_feedback table exists in the database."""
    conn = sqlite3.connect(db_file, timeout=10.0)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS task_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL UNIQUE,
            rating TEXT NOT NULL,
            recorded_at REAL NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def save_task_feedback(data_dir: Path, task_id: str, rating: str) -> None:
    """Save user feedback for a given task ID."""
    db_file = db_path(data_dir)
    init_feedback_db(db_file)
    try:
        conn = sqlite3.connect(db_file, timeout=10.0)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO task_feedback (task_id, rating, recorded_at)
            VALUES (?, ?, ?)
            """,
            (task_id, rating, time.time()),
        )
        conn.commit()
        conn.close()
        logger.info("Saved feedback '%s' for task %s", rating, task_id)
    except Exception:
        logger.exception("Failed to write task feedback to database")
