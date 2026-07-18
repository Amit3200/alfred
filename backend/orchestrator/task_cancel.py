"""Cooperative cancellation for queued agent tasks."""

from __future__ import annotations

from pathlib import Path


class TaskCancelledError(Exception):
    """Raised when a background task is cancelled while running."""


def task_is_cancelled(data_dir: Path | None, task_id: str | None) -> bool:
    if not data_dir or not task_id:
        return False
    from backend.db.sqlite_queue import SQLiteQueue

    return SQLiteQueue(data_dir).get_status(task_id) == "cancelled"


def raise_if_cancelled(data_dir: Path | None, task_id: str | None) -> None:
    if task_is_cancelled(data_dir, task_id):
        raise TaskCancelledError("Task cancelled by user")
