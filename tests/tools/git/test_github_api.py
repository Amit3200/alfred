"""Tests for GitHub App v1 API routes."""

from __future__ import annotations

import hashlib
import hmac
import json

from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.config_manager import ConfigManager
from backend.models.config import GitHubAppConfig


def _sign(body: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _client(tmp_path, *, secret: str = "whsec_test") -> tuple[TestClient, ConfigManager]:
    manager = ConfigManager(tmp_path)
    manager.init()
    config, secrets = manager.load_merged()
    config.github = GitHubAppConfig(
        enabled=True,
        client_id="Iv1.test",
        callback_base_url="https://alfred.example.dev",
    )
    secrets.github_webhook_secret = secret
    manager.save_merged(config, secrets)
    return TestClient(create_app(tmp_path)), manager


def test_github_callback_returns_html(tmp_path):
    client, _ = _client(tmp_path)
    res = client.get("/api/v1/github/callback?setup_action=install&installation_id=12345")
    assert res.status_code == 200
    assert "Alfred connected to GitHub" in res.text
    assert "installation_id=12345" in res.text
    assert "/api/v1/github/webhook" in res.text


def test_github_webhook_ping(tmp_path):
    client, _ = _client(tmp_path)
    body = json.dumps({"zen": "Keep it logically awesome."}).encode("utf-8")
    headers = {
        "X-GitHub-Event": "ping",
        "X-Hub-Signature-256": _sign(body, "whsec_test"),
    }
    res = client.post("/api/v1/github/webhook", content=body, headers=headers)
    assert res.status_code == 200
    assert res.json()["status"] == "pong"


def test_github_webhook_rejects_bad_signature(tmp_path):
    client, _ = _client(tmp_path)
    body = b'{"action":"created"}'
    res = client.post(
        "/api/v1/github/webhook",
        content=body,
        headers={
            "X-GitHub-Event": "issue_comment",
            "X-Hub-Signature-256": "sha256=bad",
        },
    )
    assert res.status_code == 401


def test_github_webhook_issue_comment_queues(tmp_path, monkeypatch):
    client, _ = _client(tmp_path)
    called: list[dict] = []

    def fake_process(payload, *, manager, processor_factory=None):
        called.append(payload)
        return "queued"

    monkeypatch.setattr("backend.api.routes.github.process_github_webhook_payload", fake_process)

    payload = {
        "action": "created",
        "comment": {
            "id": 1,
            "body": "@alfred review",
            "user": {"login": "alice", "type": "User"},
        },
        "issue": {
            "number": 7,
            "html_url": "https://github.com/org/repo/pull/7",
            "pull_request": {},
        },
        "repository": {"full_name": "org/repo"},
    }
    body = json.dumps(payload).encode("utf-8")
    res = client.post(
        "/api/v1/github/webhook",
        content=body,
        headers={
            "X-GitHub-Event": "issue_comment",
            "X-Hub-Signature-256": _sign(body, "whsec_test"),
        },
    )
    assert res.status_code == 200
    assert res.json()["status"] == "queued"
    assert called and called[0]["action"] == "created"
