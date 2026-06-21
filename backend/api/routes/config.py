"""Configuration API for the admin UI."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from backend.api.deps import get_manager, require_admin, restart_slack_listener
from backend.ai.registry import LLMRouter
from backend.config_manager import ConfigManager
from backend.health import check_ai, check_aws, check_git, check_slack
from backend.models.config import AlfredConfig, AlfredSecrets

router = APIRouter(prefix="/config", tags=["config"])


@router.get("")
def get_config(manager: ConfigManager = Depends(get_manager)) -> dict:
    if not manager.is_initialized():
        raise HTTPException(status_code=404, detail="Alfred not initialized. Run: alfred init")
    return manager.public_config()


@router.put("")
def update_config(
    payload: dict[str, Any],
    request: Request,
    manager: ConfigManager = Depends(require_admin),
) -> dict:
    config = AlfredConfig.model_validate(payload)
    _, secrets = manager.load_merged()
    manager.save_merged(config, secrets)
    slack_restart = restart_slack_listener(request)
    result = manager.public_config()
    result["slack_restart"] = slack_restart
    return result


@router.put("/secrets")
def update_secrets(
    payload: dict[str, Any],
    request: Request,
    manager: ConfigManager = Depends(require_admin),
) -> dict:
    config, secrets = manager.load_merged()
    incoming = AlfredSecrets.model_validate(payload)
    for field in (
        "slack_bot_token",
        "slack_signing_secret",
        "slack_app_token",
        "git_token",
        "aws_access_key_id",
        "aws_secret_access_key",
        "server_admin_token",
    ):
        value = getattr(incoming, field)
        if value is not None and str(value).strip():
            setattr(secrets, field, str(value).strip())
    for name, key in incoming.ai_api_keys.items():
        if key is not None and str(key).strip():
            secrets.ai_api_keys[name] = str(key).strip()
    manager._apply_secrets_to_config(config, secrets)
    manager.save_merged(config, secrets)
    slack_restart = restart_slack_listener(request)
    result = manager.public_config()
    result["slack_restart"] = slack_restart
    return result


@router.post("/restart-slack")
def restart_slack(request: Request, _: ConfigManager = Depends(require_admin)) -> dict:
    """Manually restart the Slack listener (e.g. after reinstalling the Slack app)."""
    return restart_slack_listener(request)


@router.get("/providers")
def list_providers(manager: ConfigManager = Depends(get_manager)) -> dict:
    config, _ = manager.load_merged()
    router = LLMRouter.from_config(config)
    return {"providers": router.list_providers(), "default": config.ai.default_provider}


@router.post("/providers/{provider_name}/test")
def test_provider(
    provider_name: str,
    manager: ConfigManager = Depends(require_admin),
) -> dict:
    config, _ = manager.load_merged()
    return check_ai(config, provider_name, data_dir=manager.data_dir)


@router.post("/integrations/{name}/test")
def test_integration(
    name: str,
    manager: ConfigManager = Depends(require_admin),
) -> dict:
    config, _ = manager.load_merged()
    checks = {
        "slack": check_slack,
        "git": check_git,
        "aws": check_aws,
    }
    if name not in checks:
        raise HTTPException(status_code=404, detail=f"Unknown integration: {name}")
    return checks[name](config)
