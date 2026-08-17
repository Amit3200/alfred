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
    assert progress["current_tool"] == "Writing changes"
    assert progress["progress_label"] == "Writing changes…"
    assert progress["recent_tools"] == ["Searching codebase"]


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


def test_doc_qa_progress_timeline(tmp_path: Path):
    init_checkpoint_db(db_path(tmp_path))

    from backend.observability.checkpoint import current_data_dir, current_task_id

    token_task = current_task_id.set("task-doc")
    token_dir = current_data_dir.set(tmp_path)
    try:
        log_checkpoint("process_task", "task-doc", "started")
        log_checkpoint("tool_plan", "repo.docs.qa", "completed")
        log_checkpoint("tool_plan_goal", "Answer whether mobile app integration is supported", "completed")
        log_checkpoint("tool_plan_steps", "search_repo_docs → read_repo_doc", "completed")
        log_checkpoint("route_plan", "repo_knowledge", "completed")
        log_checkpoint("graph_route", "worker", "completed")
        log_checkpoint("doc_bootstrap", "search_and_read", "started")
        log_checkpoint("doc_tool_call", "search_repo_docs", "started")
        log_checkpoint("doc_tool_call", "search_repo_docs", "completed")
        log_checkpoint("doc_found", "integrations/analytics/google-ads.mdx", "completed")
        log_checkpoint("repo_context", "FlexyPe/docs", "completed")
        log_checkpoint("doc_bootstrap", "search_and_read", "completed")
        log_checkpoint("doc_tool_call", "read_repo_doc", "started")
    finally:
        current_task_id.reset(token_task)
        current_data_dir.reset(token_dir)

    progress = latest_task_progress(tmp_path, "task-doc", task_status="running")
    labels = [step["label"] for step in progress["progress_steps"]]
    assert "Understanding your question" in labels
    assert "Plan: Documentation Q&A" in labels
    assert "Matched documentation question" in labels
    assert "Investigating with agent" in labels
    assert "Searching documentation" in labels
    assert any("google-ads.mdx" in label for label in labels)
    assert progress["progress_steps"][-1]["label"] == "Reading documentation"
    assert progress["progress_steps"][-1]["status"] == "active"
    assert progress["progress_plan"]["intent"] == "repo.docs.qa"
    assert progress["progress_plan"]["steps"] == ["search_repo_docs", "read_repo_doc"]


def test_format_doc_search_progress():
    label = format_checkpoint_progress("doc_tool_call", "search_repo_docs", "started")
    assert label == "Searching documentation…"
