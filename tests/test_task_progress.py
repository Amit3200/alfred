"""Tests for chat task progress labels."""

from __future__ import annotations

from pathlib import Path

from backend.observability.checkpoint import init_checkpoint_db, log_checkpoint
from backend.observability.task_progress import (
    format_checkpoint_progress,
    latest_task_progress,
    load_task_checkpoints,
)
from backend.paths import db_path


def test_format_checkpoint_progress_tool_started():
    label = format_checkpoint_progress("git_tool_call", "grep_repo", "started")
    assert label == "Searching codebase…"


def test_format_checkpoint_progress_tool_completed():
    label = format_checkpoint_progress("git_tool_call", "create_pull_request", "completed")
    assert label == "Opening pull request — done"


def test_latest_task_progress_shows_current_tool(tmp_path: Path):
    db_file = db_path(tmp_path)
    init_checkpoint_db(db_file)

    from backend.observability.checkpoint import current_data_dir, current_task_id

    token_task = current_task_id.set("task-123")
    token_dir = current_data_dir.set(tmp_path)
    try:
        log_checkpoint("process_task", "task-123", "started")
        log_checkpoint("git_tool_call", "grep_repo", "started")
        log_checkpoint("git_tool_call", "grep_repo", "completed")
        log_checkpoint("git_tool_call", "write_file", "started")
    finally:
        current_task_id.reset(token_task)
        current_data_dir.reset(token_dir)

    rows = load_task_checkpoints(tmp_path, "task-123")
    assert len(rows) == 4

    progress = latest_task_progress(tmp_path, "task-123", task_status="running")
    assert progress["current_tool"] == "write_file"
    assert progress["progress_label"] == "Writing changes…"
    assert progress["recent_tools"] == ["grep_repo"]


def test_latest_task_progress_planning_after_tool_done(tmp_path: Path):
    db_file = db_path(tmp_path)
    init_checkpoint_db(db_file)

    from backend.observability.checkpoint import current_data_dir, current_task_id

    token_task = current_task_id.set("task-456")
    token_dir = current_data_dir.set(tmp_path)
    try:
        log_checkpoint("git_tool_call", "grep_repo", "started")
        log_checkpoint("git_tool_call", "grep_repo", "completed")
    finally:
        current_task_id.reset(token_task)
        current_data_dir.reset(token_dir)

    progress = latest_task_progress(tmp_path, "task-456", task_status="running")
    assert progress["progress_label"] == "Planning next step…"
    assert progress["current_tool"] is None
