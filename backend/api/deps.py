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


def require_admin(
    manager: ConfigManager = Depends(get_manager),
    x_alfred_token: str | None = Header(default=None, alias="X-Alfred-Token"),
) -> ConfigManager:
    config, secrets = manager.load_merged()
    expected = (secrets.server_admin_token or config.server.admin_token or "").strip()
    provided = (x_alfred_token or "").strip()
    if expected and provided != expected:
        raise HTTPException(status_code=401, detail="Invalid admin token")
    return manager
