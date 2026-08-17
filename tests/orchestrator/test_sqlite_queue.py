"""Tests for the SQLite-backed task queue."""

from __future__ import annotations

from pathlib import Path
from backend.db.sqlite_queue import SQLiteQueue


def test_sqlite_queue_push_pop_ack(tmp_path: Path):
    queue = SQLiteQueue(data_dir=tmp_path)

    task = {
        "id": "test-task-1",
        "source": "slack",
        "user_id": "U123",
        "channel_id": "C123",
        "raw_text": "hello",
        "cleaned_intent": "hello",
    }

    # Push task
    task_id = queue.push(task)
    assert task_id == "test-task-1"

    # Pop task
    popped = queue.pop()
    assert popped is not None
    assert popped["id"] == "test-task-1"
    assert popped["cleaned_intent"] == "hello"

    # Pop again should be empty since task status changed to running
    assert queue.pop() is None

    # Ack task
    queue.ack("test-task-1")
