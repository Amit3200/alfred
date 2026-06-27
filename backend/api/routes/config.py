"""Configuration API for the admin UI."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pathlib import Path
import tempfile

from backend.api.deps import get_manager, require_admin, restart_slack_listener
from backend.ai.registry import LLMRouter
from backend.config_manager import ConfigManager
from backend.config_transfer import ConfigImportError, build_export_zip, import_config_zip
from backend.health import check_ai, check_aws, check_git, check_google, check_jira, check_slack
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
        "github_webhook_secret",
        "github_client_secret",
        "aws_access_key_id",
        "aws_secret_access_key",
        "jira_api_token",
        "google_credentials_json",
        "google_oauth_refresh_token",
        "server_admin_token",
        "server_admin_username",
        "server_admin_password",
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
        "jira": check_jira,
        "google": check_google,
    }
    if name not in checks:
        raise HTTPException(status_code=404, detail=f"Unknown integration: {name}")
    return checks[name](config)


@router.get("/export")
def export_config(manager: ConfigManager = Depends(require_admin)) -> FileResponse:
    """Export settings, secrets, encryption key, playbooks, and branding as a zip."""
    zip_path = Path(tempfile.gettempdir()) / "alfred-config-export.zip"
    try:
        build_export_zip(manager.data_dir, zip_path)
    except ConfigImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return FileResponse(
        path=zip_path,
        filename="alfred-config.zip",
        media_type="application/zip",
    )


@router.post("/import")
async def import_config(
    request: Request,
    file: UploadFile = File(...),
    manager: ConfigManager = Depends(require_admin),
) -> dict:
    """Import an Alfred config zip exported from another instance."""
    content = await file.read()
    try:
        imported = import_config_zip(manager.data_dir, content)
    except ConfigImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    slack_restart = restart_slack_listener(request)
    result = manager.public_config()
    result["imported_files"] = imported
    result["slack_restart"] = slack_restart
    return result
