"""Tests for async task queue processing, SQLite checkpoints, and JIRA key caching."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.db.session_store import SessionStore
from backend.db.sqlite_queue import SQLiteQueue
from backend.models.config import AlfredConfig
from backend.models.task import Task
from backend.observability.checkpoint import (
    current_data_dir,
    current_task_id,
    init_checkpoint_db,
    log_checkpoint,
)
from backend.orchestrator.processor import TaskProcessor
from backend.paths import db_path
from backend.routing.git.context import enrich_tool_arguments
from backend.routing.jira.direct import detect_jira_direct_action
from backend.tools.result import ToolResult


def test_sqlite_queue_get_status(tmp_path: Path):
    queue = SQLiteQueue(tmp_path)
    task_dict = {
        "id": "test-task-1",
        "source": "ui",
        "user_id": "test-user",
        "channel_id": "session-1",
        "thread_ts": "session-1",
        "raw_text": "hello alfred",
        "cleaned_intent": "hello alfred",
        "status": "pending",
        "created_at": time.time(),
        "updated_at": time.time(),
    }
    queue.push(task_dict)
    assert queue.get_status("test-task-1") == "pending"

    task = queue.pop()
    assert task is not None
    assert queue.get_status("test-task-1") == "running"

    queue.ack("test-task-1")
    assert queue.get_status("test-task-1") == "completed"


def test_context_vars_and_db_logging(tmp_path: Path):
    db_file = db_path(tmp_path)
    init_checkpoint_db(db_file)

    token_task = current_task_id.set("task-abc")
    token_dir = current_data_dir.set(tmp_path)

    try:
        log_checkpoint("test_checkpoint", "my_func", "started")
    finally:
        current_task_id.reset(token_task)
        current_data_dir.reset(token_dir)

    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    cursor.execute("SELECT task_id, checkpoint, function_name, status FROM task_checkpoints")
    row = cursor.fetchone()
    conn.close()

    assert row is not None
    assert row[0] == "task-abc"
    assert row[1] == "test_checkpoint"
    assert row[2] == "my_func"
    assert row[3] == "started"


def test_jira_key_caching_and_enrichment():
    config = AlfredConfig()
    config.jira.enabled = True

    # Check direct JIRA action uses cached key if input doesn't have it
    mock_session = MagicMock()
    mock_session.metadata = {"active_jira_ticket": "ENG-456"}

    action = detect_jira_direct_action(
        "what is the status of that ticket?",
        config,
        session=mock_session,
    )
    assert action is not None
    assert action[0] == "get_jira_issue"
    assert action[1]["issue_key"] == "ENG-456"

    # Verify tool argument enrichment inserts cached key
    enriched = enrich_tool_arguments(
        "get_jira_issue",
        {},
        config.git,
        mock_session,
    )
    assert enriched.get("issue_key") == "ENG-456"


def test_checkpoints_api_route(tmp_path: Path):
    db_file = db_path(tmp_path)
    init_checkpoint_db(db_file)

    # Insert a dummy checkpoint
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO task_checkpoints (task_id, checkpoint, function_name, status, timestamp)
        VALUES ('task-123', 'jira_tool_call', 'get_issue', 'completed', 12345.6)
        """
    )
    conn.commit()
    conn.close()

    app = create_app(data_dir=tmp_path)
    # Stop background tasks to avoid interference
    if hasattr(app.state, "queue_worker"):
        app.state.queue_worker.stop()
    if hasattr(app.state, "slack_runner"):
        app.state.slack_runner.stop()

    from backend.api.deps import require_admin
    from backend.config_manager import ConfigManager
    manager = ConfigManager(tmp_path)
    app.dependency_overrides[require_admin] = lambda: manager

    client = TestClient(app)
    headers = {"X-Alfred-Token": "secret"}
    response = client.get("/api/observability/checkpoints?task_id=task-123", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data["checkpoints"]) == 1
    assert data["checkpoints"][0]["checkpoint"] == "jira_tool_call"
    assert data["checkpoints"][0]["function_name"] == "get_issue"
    assert data["checkpoints"][0]["status"] == "completed"
