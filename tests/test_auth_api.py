"""Tests for backend Authentication and secure routes."""

from __future__ import annotations

import base64
from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.config_manager import ConfigManager


def _client(tmp_path) -> tuple[TestClient, ConfigManager]:
    manager = ConfigManager(tmp_path)
    # Initialize config with specific credentials
    manager.init(
        force=True,
        username="custom_admin",
        password="custom_password",
        token="custom_token_123",
    )
    app = create_app(tmp_path)
    return TestClient(app), manager


def test_login_success(tmp_path):
    client, _ = _client(tmp_path)
    
    # Try valid credentials
    res = client.post("/api/auth/login", json={"username": "custom_admin", "password": "custom_password"})
    assert res.status_code == 200
    assert res.json() == {"token": "custom_token_123"}


def test_login_failure(tmp_path):
    client, _ = _client(tmp_path)
    
    # Try invalid password
    res = client.post("/api/auth/login", json={"username": "custom_admin", "password": "wrong_password"})
    assert res.status_code == 401
    
    # Try invalid username
    res = client.post("/api/auth/login", json={"username": "wrong_user", "password": "custom_password"})
    assert res.status_code == 401


def test_token_auth_on_protected_endpoint(tmp_path):
    client, _ = _client(tmp_path)
    
    # Access protected route with X-Alfred-Token
    res = client.get("/api/config", headers={"X-Alfred-Token": "custom_token_123"})
    assert res.status_code == 200
    
    # Access with invalid X-Alfred-Token
    res = client.get("/api/config", headers={"X-Alfred-Token": "wrong_token"})
    assert res.status_code == 401
    
    # Access with no token
    res = client.get("/api/config")
    assert res.status_code == 401


def test_bearer_auth_on_protected_endpoint(tmp_path):
    client, _ = _client(tmp_path)
    
    # Access protected route with Bearer token
    res = client.get("/api/config", headers={"Authorization": "Bearer custom_token_123"})
    assert res.status_code == 200
    
    # Access with invalid Bearer token
    res = client.get("/api/config", headers={"Authorization": "Bearer wrong_token"})
    assert res.status_code == 401


def test_basic_auth_on_protected_endpoint(tmp_path):
    client, _ = _client(tmp_path)
    
    # Access protected route with valid Basic auth
    creds = base64.b64encode(b"custom_admin:custom_password").decode("utf-8")
    res = client.get("/api/config", headers={"Authorization": f"Basic {creds}"})
    assert res.status_code == 200
    
    # Access with invalid Basic auth password
    bad_creds = base64.b64encode(b"custom_admin:wrong_password").decode("utf-8")
    res = client.get("/api/config", headers={"Authorization": f"Basic {bad_creds}"})
    assert res.status_code == 401


def test_auto_migration_for_existing_secrets(tmp_path):
    manager = ConfigManager(tmp_path)
    # Initialize with default/classic format (only token present)
    manager.init(force=True)
    
    # Wipe credentials fields from secrets to simulate an old deployment
    secrets = manager.load_secrets()
    secrets.server_admin_username = ""
    secrets.server_admin_password = ""
    manager.save_secrets(secrets)
    
    # Loading secrets should now auto-generate default username and a secure password
    reloaded = manager.load_secrets()
    assert reloaded.server_admin_username == "admin"
    assert len(reloaded.server_admin_password) > 0
    assert len(reloaded.server_admin_token) > 0
