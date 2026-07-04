"""Google OAuth API for admin UI."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse

from backend.api.deps import get_manager, require_admin
from backend.config_manager import ConfigManager
from backend.integrations.google.credentials import credentials_json_type, google_libs_available
from backend.integrations.google.oauth import begin_oauth, finish_oauth, pop_oauth_session

admin_router = APIRouter(prefix="/config/google", tags=["google"])
public_router = APIRouter(prefix="/config/google", tags=["google"])


def _redirect_base(config, request: Request) -> str:
    base = (config.google.oauth_redirect_base_url or "").strip().rstrip("/")
    if base:
        return base
    return str(request.base_url).rstrip("/")


def _callback_uri(config, request: Request) -> str:
    return f"{_redirect_base(config, request)}/api/config/google/oauth/callback"


def _oauth_status(config, secrets, request: Request | None = None) -> dict[str, Any]:
    raw = (secrets.google_credentials_json or "").strip()
    cred_type: str | None = None
    if raw:
        try:
            cred_type = credentials_json_type(raw)
        except ValueError:
            cred_type = "invalid"
    connected = bool(
        cred_type == "service_account"
        or (cred_type == "oauth_client" and secrets.google_oauth_refresh_token.strip())
    )
    redirect_uri = None
    if request is not None:
        redirect_uri = _callback_uri(config, request)
    return {
        "credentials_configured": bool(raw),
        "credentials_type": cred_type,
        "oauth_connected": connected,
        "oauth_refresh_token_configured": bool(secrets.google_oauth_refresh_token.strip()),
        "google_libs_installed": google_libs_available(),
        "redirect_uri": redirect_uri,
    }


@admin_router.get("/oauth/status")
def google_oauth_status(
    request: Request,
    manager: ConfigManager = Depends(get_manager),
) -> dict:
    config, secrets = manager.load_merged()
    return _oauth_status(config, secrets, request)


@admin_router.post("/oauth/start")
def google_oauth_start(
    request: Request,
    manager: ConfigManager = Depends(require_admin),
) -> dict:
    if not google_libs_available():
        raise HTTPException(
            status_code=400,
            detail="Install Google libraries: pip install 'alfred-agent[google]'",
        )
    config, secrets = manager.load_merged()
    raw = (secrets.google_credentials_json or "").strip()
    if not raw:
        raise HTTPException(
            status_code=400,
            detail="Paste OAuth client JSON in Secrets first, then save.",
        )
    try:
        cred_type = credentials_json_type(raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if cred_type != "oauth_client":
        raise HTTPException(
            status_code=400,
            detail="Connect Google is only for OAuth client credentials. Service accounts work after saving JSON.",
        )

    redirect_uri = _callback_uri(config, request)
    try:
        _, url = begin_oauth(raw, redirect_uri=redirect_uri, data_dir=manager.data_dir)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"authorization_url": url, "redirect_uri": redirect_uri}


@public_router.get("/oauth/callback")
def google_oauth_callback(
    request: Request,
    code: str = "",
    state: str = "",
    error: str = "",
    manager: ConfigManager = Depends(get_manager),
) -> HTMLResponse:
    if error:
        return HTMLResponse(
            _html_page("Google connection failed", f"Google returned an error: {error}"),
            status_code=400,
        )
    if not code or not state:
        return HTMLResponse(
            _html_page("Google connection failed", "Missing authorization code or state."),
            status_code=400,
        )
    session = pop_oauth_session(manager.data_dir, state)
    if not session:
        return HTMLResponse(
            _html_page(
                "Google connection failed",
                "Invalid or expired OAuth state. Start Connect Google again from Integrations.",
            ),
            status_code=400,
        )

    config, secrets = manager.load_merged()
    raw = (secrets.google_credentials_json or "").strip()
    if not raw:
        return HTMLResponse(
            _html_page("Google connection failed", "OAuth client JSON not configured."),
            status_code=400,
        )

    try:
        result = finish_oauth(
            raw,
            code=code,
            redirect_uri=session["redirect_uri"],
            code_verifier=session.get("code_verifier"),
        )
    except Exception as exc:
        return HTMLResponse(
            _html_page("Google connection failed", str(exc)),
            status_code=400,
        )

    secrets.google_oauth_refresh_token = str(result["refresh_token"])
    manager._apply_secrets_to_config(config, secrets)
    manager.save_merged(config, secrets)

    return HTMLResponse(
        _html_page(
            "Google connected",
            "Alfred can now access Google Sheets and Docs. You can close this tab and return to the admin console.",
            ok=True,
        )
    )


def _html_page(title: str, message: str, *, ok: bool = False) -> str:
    color = "#16a34a" if ok else "#dc2626"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <title>{title}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; max-width: 36rem; margin: 4rem auto; padding: 0 1rem; }}
    h1 {{ color: {color}; font-size: 1.5rem; }}
    p {{ line-height: 1.5; color: #334155; }}
  </style>
</head>
<body>
  <h1>{title}</h1>
  <p>{message}</p>
</body>
</html>"""
