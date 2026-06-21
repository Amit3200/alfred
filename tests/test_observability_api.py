"""Tests for observability API routes."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.config_manager import ConfigManager
from backend.observability.models import InteractionEvent
from backend.observability.store import SQLiteObservabilityStore


@pytest.fixture
def client(tmp_path):
    manager = ConfigManager(tmp_path)
    manager.init()
    _, secrets = manager.load_merged()
    admin_token = secrets.server_admin_token

    store = SQLiteObservabilityStore(tmp_path)
    store.record(
        InteractionEvent(
            recorded_at=datetime.now(timezone.utc),
            event_type="llm_call",
            source="slack",
            user_id="U1",
            user_label="amit",
            provider="kimi",
            model="kimi-k2.6",
            total_tokens=42,
        )
    )

    app = create_app(tmp_path)
    return TestClient(app), admin_token


def test_observability_summary_requires_admin(client):
    test_client, admin_token = client
    denied = test_client.get("/api/observability/summary")
    assert denied.status_code == 401

    ok = test_client.get(
        "/api/observability/summary",
        headers={"X-Alfred-Token": admin_token},
    )
    assert ok.status_code == 200
    body = ok.json()
    assert body["summary"]["llm_calls"] == 1
    assert body["summary"]["total_tokens"] == 42
