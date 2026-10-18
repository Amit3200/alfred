"""Tests for HTML artifact upload and public serving."""

from __future__ import annotations

import hashlib

from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.config_manager import ConfigManager

SAMPLE_HTML = """<!DOCTYPE html>
<html><head><title>Test</title></head>
<body><h1>Hello artifacts</h1></body></html>
"""


def _client(tmp_path) -> tuple[TestClient, str]:
    manager = ConfigManager(tmp_path)
    manager.init()
    _, secrets = manager.load_merged()
    admin_token = secrets.server_admin_token or "test-admin-token"
    app = create_app(tmp_path)
    return TestClient(app), admin_token


def _actor_headers(
    token: str,
    *,
    user: str = "tester",
    actor_key: str | None = None,
) -> dict[str, str]:
    return {
        "X-Alfred-Token": token,
        "X-Alfred-User": user,
        "X-Alfred-Actor-Key": actor_key or f"admin:{user}",
    }


def test_upload_and_serve_latest_by_slug(tmp_path):
    client, token = _client(tmp_path)
    headers = _actor_headers(token)

    res = client.post(
        "/api/artifacts",
        headers=headers,
        json={"slug": "demo-deck", "title": "Demo", "html": SAMPLE_HTML},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    sha = body["artifact"]["sha256"]
    assert sha == hashlib.sha256(SAMPLE_HTML.encode()).hexdigest()
    assert body["artifact"]["slug_url"] == "/artifacts/s/demo-deck"

    public = client.get("/artifacts/s/demo-deck")
    assert public.status_code == 200
    assert "Hello artifacts" in public.text


def test_slug_update_serves_latest_sha(tmp_path):
    client, token = _client(tmp_path)
    headers = _actor_headers(token)
    slug = "redirection-2025"

    html_v1 = SAMPLE_HTML.replace("Hello artifacts", "Version one")
    html_v2 = SAMPLE_HTML.replace("Hello artifacts", "Version two")

    r1 = client.post("/api/artifacts", headers=headers, json={"slug": slug, "html": html_v1})
    r2 = client.post("/api/artifacts", headers=headers, json={"slug": slug, "html": html_v2})
    sha1 = r1.json()["artifact"]["sha256"]
    sha2 = r2.json()["artifact"]["sha256"]
    assert sha1 != sha2

    latest = client.get(f"/artifacts/s/{slug}")
    assert latest.status_code == 200
    assert "Version two" in latest.text

    old = client.get(f"/artifacts/sha/{sha1}")
    assert old.status_code == 200
    assert "Version one" in old.text


def test_mine_lists_only_owned_latest_per_slug(tmp_path):
    client, token = _client(tmp_path)
    alice = _actor_headers(token, user="alice")
    bob = _actor_headers(token, user="bob")

    client.post("/api/artifacts", headers=alice, json={"slug": "metrics-q1", "html": SAMPLE_HTML})
    client.post(
        "/api/artifacts",
        headers=alice,
        json={"slug": "metrics-q1", "html": SAMPLE_HTML + "<!-- v2 -->"},
    )
    client.post("/api/artifacts", headers=bob, json={"slug": "bob-deck", "html": SAMPLE_HTML})

    alice_list = client.get("/api/artifacts/mine", headers=alice)
    assert alice_list.status_code == 200
    alice_body = alice_list.json()
    assert alice_body["count"] == 1
    assert alice_body["artifacts"][0]["slug"] == "metrics-q1"

    bob_list = client.get("/api/artifacts/mine", headers=bob)
    assert bob_list.status_code == 200
    assert bob_list.json()["count"] == 1
    assert bob_list.json()["artifacts"][0]["slug"] == "bob-deck"

    meta = client.get("/api/artifacts/metrics-q1", headers=alice)
    assert meta.status_code == 200
    assert len(meta.json()["versions"]) == 2


def test_cannot_manage_or_overwrite_other_users_slug(tmp_path):
    client, token = _client(tmp_path)
    alice = _actor_headers(token, user="alice")
    bob = _actor_headers(token, user="bob")

    client.post("/api/artifacts", headers=alice, json={"slug": "team-review", "html": SAMPLE_HTML})

    bob_meta = client.get("/api/artifacts/team-review", headers=bob)
    assert bob_meta.status_code == 403

    bob_upload = client.post(
        "/api/artifacts",
        headers=bob,
        json={"slug": "team-review", "html": SAMPLE_HTML + "<!-- hijack -->"},
    )
    assert bob_upload.status_code == 403

    public = client.get("/artifacts/s/team-review")
    assert public.status_code == 200
    assert "hijack" not in public.text


def test_slack_actor_key(tmp_path):
    client, token = _client(tmp_path)
    headers = {
        "X-Alfred-Token": token,
        "X-Alfred-User": "Om Sinkar",
        "X-Alfred-Actor-Key": "slack:U01234567",
    }
    client.post("/api/artifacts", headers=headers, json={"slug": "slack-deck", "html": SAMPLE_HTML})

    mine = client.get("/api/artifacts/mine", headers=headers)
    assert mine.status_code == 200
    assert mine.json()["count"] == 1
    assert mine.json()["actor"]["key"] == "slack:U01234567"


def test_rejects_non_html(tmp_path):
    client, token = _client(tmp_path)
    headers = _actor_headers(token)

    res = client.post(
        "/api/artifacts",
        headers=headers,
        json={"slug": "bad", "html": "plain text only"},
    )
    assert res.status_code == 400


def test_invalid_slug(tmp_path):
    client, token = _client(tmp_path)
    headers = _actor_headers(token)

    res = client.post(
        "/api/artifacts",
        headers=headers,
        json={"slug": "Bad Slug!", "html": SAMPLE_HTML},
    )
    assert res.status_code == 400


def test_requires_actor_header(tmp_path):
    client, token = _client(tmp_path)
    res = client.get("/api/artifacts/mine", headers={"X-Alfred-Token": token})
    assert res.status_code == 400


def test_delete_version_promotes_previous_and_keeps_slug(tmp_path):
    client, token = _client(tmp_path)
    headers = _actor_headers(token)
    slug = "daily-metrics"
    v1 = SAMPLE_HTML.replace("Hello artifacts", "Day one")
    v2 = SAMPLE_HTML.replace("Hello artifacts", "Day two")
    r1 = client.post("/api/artifacts", headers=headers, json={"slug": slug, "html": v1})
    r2 = client.post("/api/artifacts", headers=headers, json={"slug": slug, "html": v2})
    sha1 = r1.json()["artifact"]["sha256"]
    sha2 = r2.json()["artifact"]["sha256"]

    mine = client.get("/api/artifacts/mine", headers=headers).json()
    assert mine["count"] == 1
    assert mine["artifacts"][0]["version_count"] == 2

    deleted = client.delete(f"/api/artifacts/{slug}/versions/{sha2}", headers=headers)
    assert deleted.status_code == 200
    body = deleted.json()
    assert body["slug_removed"] is False
    assert body["latest"]["sha256"] == sha1

    latest = client.get(f"/artifacts/s/{slug}")
    assert latest.status_code == 200
    assert "Day one" in latest.text
    assert client.get(f"/artifacts/sha/{sha2}").status_code == 404


def test_delete_last_version_removes_slug(tmp_path):
    client, token = _client(tmp_path)
    headers = _actor_headers(token)
    res = client.post(
        "/api/artifacts",
        headers=headers,
        json={"slug": "gone-deck", "html": SAMPLE_HTML},
    )
    sha = res.json()["artifact"]["sha256"]
    deleted = client.delete(f"/api/artifacts/gone-deck/versions/{sha}", headers=headers)
    assert deleted.status_code == 200
    assert deleted.json()["slug_removed"] is True
    assert client.get("/artifacts/s/gone-deck").status_code == 404
    assert client.get("/api/artifacts/mine", headers=headers).json()["count"] == 0


def test_cannot_delete_other_users_version(tmp_path):
    client, token = _client(tmp_path)
    alice = _actor_headers(token, user="alice")
    bob = _actor_headers(token, user="bob")
    res = client.post("/api/artifacts", headers=alice, json={"slug": "alice-deck", "html": SAMPLE_HTML})
    sha = res.json()["artifact"]["sha256"]
    denied = client.delete(f"/api/artifacts/alice-deck/versions/{sha}", headers=bob)
    assert denied.status_code == 403
    assert client.get("/artifacts/s/alice-deck").status_code == 200