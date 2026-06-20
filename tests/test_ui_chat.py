"""Tests for admin UI chat API."""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.config_manager import ConfigManager


def _client(tmp_path) -> tuple[TestClient, str]:
    manager = ConfigManager(tmp_path)
    manager.init()
    _, secrets = manager.load_merged()
    admin_token = secrets.server_admin_token or "test-admin-token"
    app = create_app(tmp_path)
    return TestClient(app), admin_token


def test_ui_chat_session_lifecycle(tmp_path):
    client, admin_token = _client(tmp_path)
    headers = {"X-Alfred-Token": admin_token}

    created = client.post("/api/chat/sessions", headers=headers, json={"title": "Test"})
    assert created.status_code == 200
    chat_id = created.json()["id"]

    listed = client.get("/api/chat/sessions", headers=headers)
    assert listed.status_code == 200
    assert any(s["id"] == chat_id for s in listed.json()["sessions"])

    detail = client.get(f"/api/chat/sessions/{chat_id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["messages"] == []


def test_ui_chat_export_message(tmp_path):
    from unittest.mock import patch

    client, admin_token = _client(tmp_path)
    headers = {"X-Alfred-Token": admin_token}

    chat_id = client.post("/api/chat/sessions", headers=headers, json={}).json()["id"]

    with patch("backend.ingress.ui_chat.TaskProcessor") as mock_cls:
        from backend.models.response import AssistantResponse

        mock_cls.return_value.process.return_value = AssistantResponse.from_text(
            "Here is your summary."
        )
        sent = client.post(
            f"/api/chat/sessions/{chat_id}/messages",
            headers=headers,
            json={"content": "summarize my open prs"},
        )
    assert sent.status_code == 200
    assert "summary" in sent.json()["reply"].lower()

    export_msg = client.post(
        f"/api/chat/sessions/{chat_id}/messages",
        headers=headers,
        json={"content": "export this conversation to markdown"},
    )
    assert export_msg.status_code == 200
    body = export_msg.json()
    assert "export" in body
    filename = body["export"]["filename"]

    download = client.get(f"/api/chat/exports/{filename}", headers=headers)
    assert download.status_code == 200
    assert b"summarize my open prs" in download.content


def test_wants_export_markdown():
    from backend.ingress.chat_export import wants_export_markdown

    assert wants_export_markdown("summarize and export to MD file")
    assert wants_export_markdown("export this chat")
    assert not wants_export_markdown("hello")
