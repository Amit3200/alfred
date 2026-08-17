"""Shared API dependencies."""

from __future__ import annotations

import logging

from fastapi import Depends, Header, HTTPException, Request

from backend.config_manager import ConfigManager

logger = logging.getLogger(__name__)


def get_manager(request: Request) -> ConfigManager:
    return request.app.state.config_manager


def restart_slack_listener(request: Request) -> dict:
    """Restart Slack Socket Mode listener to pick up new tokens/config."""
    runner = getattr(request.app.state, "slack_runner", None)
    if runner is None:
        return {"ok": False, "message": "Slack runner not available"}
    ok, message = runner.restart()
    return {"ok": ok, "message": message}


import base64

def require_admin(
    manager: ConfigManager = Depends(get_manager),
    x_alfred_token: str | None = Header(default=None, alias="X-Alfred-Token"),
    authorization: str | None = Header(default=None),
) -> ConfigManager:
    config, secrets = manager.load_merged()
    expected_token = (secrets.server_admin_token or config.server.admin_token or "").strip()
    
    # Check X-Alfred-Token header
    provided_token = (x_alfred_token or "").strip()
    if expected_token and provided_token == expected_token:
        return manager
        
    # Check Authorization header
    if authorization:
        auth_lower = authorization.lower()
        if auth_lower.startswith("basic "):
            try:
                encoded = authorization.split(" ", 1)[1]
                decoded = base64.b64decode(encoded).decode("utf-8")
                user, password = decoded.split(":", 1)
                expected_user = (secrets.server_admin_username or config.server.admin_username or "admin").strip()
                expected_pass = (secrets.server_admin_password or config.server.admin_password or "").strip()
                if user.strip() == expected_user and password.strip() == expected_pass:
                    return manager
            except Exception:
                pass
        elif auth_lower.startswith("bearer "):
            try:
                provided_bearer = authorization.split(" ", 1)[1].strip()
                if expected_token and provided_bearer == expected_token:
                    return manager
            except Exception:
                pass

    raise HTTPException(status_code=401, detail="Unauthorized")


def get_artifact_actor(
    x_alfred_user: str | None = Header(default=None, alias="X-Alfred-User"),
    x_alfred_actor_key: str | None = Header(default=None, alias="X-Alfred-Actor-Key"),
) -> "ArtifactActor":
    """Resolve the human actor for artifact management (admin UI or Slack)."""
    from backend.artifacts.actor import ArtifactActor, normalize_actor_key

    label = (x_alfred_user or "").strip()
    if not label:
        raise HTTPException(
            status_code=400,
            detail="X-Alfred-User header required (admin username or Slack display name)",
        )
    raw_key = (x_alfred_actor_key or "").strip()
    key = raw_key or normalize_actor_key(label)
    return ArtifactActor(key=key, label=label)
