"""Tests for SQLite maintenance API."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.config_manager import ConfigManager
from backend.observability.models import InteractionEvent
from backend.observability.store import SQLiteObservabilityStore
from backend.db.db_maintenance import get_db_stats
from backend.db.session_store import SessionStore


def _client(tmp_path) -> tuple[TestClient, str, ConfigManager]:
    manager = ConfigManager(tmp_path)
    manager.init()
    _, secrets = manager.load_merged()
    admin_token = secrets.server_admin_token or "test-admin-token"
    app = create_app(tmp_path)
    return TestClient(app), admin_token, manager


def _seed_events(manager: ConfigManager, count: int = 3) -> None:
    store = SQLiteObservabilityStore(manager.data_dir)
    now = datetime.now(timezone.utc)
    for i in range(count):
        store.record(
            InteractionEvent(
                recorded_at=now - timedelta(days=i * 20),
                event_type="tool_call",
                source="ui",
                user_id="U1",
                user_label="tester",
                tool_name="grep_repo",
                tool_category="git",
            )
        )


def test_get_db_stats(tmp_path):
    client, admin_token, manager = _client(tmp_path)
    headers = {"X-Alfred-Token": admin_token}
    _seed_events(manager, 2)

    res = client.get("/api/storage/db", headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body["tables"]["interaction_events"]["rows"] == 2
    assert body["size_bytes"] > 0


def test_cleanup_observability_older_than_days(tmp_path):
    client, admin_token, manager = _client(tmp_path)
    headers = {"X-Alfred-Token": admin_token}
    _seed_events(manager, 3)

    res = client.post(
        "/api/storage/db/cleanup",
        headers=headers,
        json={"scope": "observability", "older_than_days": 15, "vacuum": False},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["removed"]["interaction_events"] == 2

    stats = get_db_stats(manager.data_dir)
    assert stats["tables"]["interaction_events"]["rows"] == 1


def test_cleanup_sessions(tmp_path):
    client, admin_token, manager = _client(tmp_path)
    headers = {"X-Alfred-Token": admin_token}
    sessions = SessionStore(manager.data_dir)
    sessions.append_exchange(
        "slack:C1:thread",
        source="slack",
        scope_id="C1",
        thread_id="thread",
        user_content="hi",
        assistant_content="hello",
    )

    res = client.post(
        "/api/storage/db/cleanup",
        headers=headers,
        json={"scope": "sessions", "vacuum": False},
    )
    assert res.status_code == 200
    assert res.json()["removed"]["conversation_sessions"] == 1
    assert sessions.load("slack:C1:thread") is None
