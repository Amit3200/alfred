"""GitHub App webhook and OAuth callback endpoints."""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from backend.github.client import exchange_oauth_code
from backend.github.handler import process_github_webhook_payload
from backend.github.verify import verify_github_signature

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/github", tags=["github"])


@router.get("/callback")
async def github_oauth_callback(request: Request) -> HTMLResponse:
    """OAuth / post-install redirect from GitHub App settings."""
    manager = request.app.state.config_manager
    config, _ = manager.load_merged()
    params = dict(request.query_params)
    setup_action = params.get("setup_action", "")
    installation_id = params.get("installation_id", "")
    code = params.get("code", "")

    oauth_result: dict[str, Any] | None = None
    callback_base = (config.github.callback_base_url or str(request.base_url)).rstrip("/")
    redirect_uri = f"{callback_base}/api/v1/github/callback"

    if code and config.github.client_id and config.github.client_secret:
        try:
            oauth_result = exchange_oauth_code(
                client_id=config.github.client_id,
                client_secret=config.github.client_secret,
                code=code,
                redirect_uri=redirect_uri,
            )
            logger.info("GitHub OAuth callback succeeded for installation %s", installation_id)
        except Exception:
            logger.exception("GitHub OAuth code exchange failed")

    title = "Alfred connected to GitHub"
    if setup_action == "install":
        subtitle = f"App installed (installation_id={installation_id or 'unknown'})."
    elif setup_action == "update":
        subtitle = f"App updated (installation_id={installation_id or 'unknown'})."
    elif code:
        subtitle = "OAuth authorization received."
    else:
        subtitle = "Callback URL is reachable."

    oauth_line = ""
    if oauth_result and oauth_result.get("access_token"):
        oauth_line = "<p>User access token exchanged successfully.</p>"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>{title}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; max-width: 40rem; margin: 4rem auto; padding: 0 1rem; }}
    h1 {{ font-size: 1.5rem; }}
    code {{ background: #f4f4f5; padding: 0.1rem 0.35rem; border-radius: 4px; }}
  </style>
</head>
<body>
  <h1>{title}</h1>
  <p>{subtitle}</p>
  {oauth_line}
  <p>Webhook URL: <code>{callback_base}/api/v1/github/webhook</code></p>
  <p>Enable GitHub ingress in Alfred config (<code>github.enabled: true</code>) and paste the webhook secret in Admin → Secrets.</p>
</body>
</html>"""
    return HTMLResponse(content=html)


@router.post("/webhook")
async def github_webhook(request: Request) -> JSONResponse:
    """Receive GitHub App webhooks (issue_comment on PRs)."""
    manager = request.app.state.config_manager
    config, _ = manager.load_merged()

    body = await request.body()
    event = request.headers.get("X-GitHub-Event", "")
    delivery = request.headers.get("X-GitHub-Delivery", "")

    secret = config.github.webhook_secret
    signature = request.headers.get("X-Hub-Signature-256")
    if secret:
        if not verify_github_signature(body, signature, secret):
            logger.warning("GitHub webhook signature verification failed delivery=%s", delivery)
            raise HTTPException(status_code=401, detail="Invalid webhook signature")
    elif event != "ping":
        logger.warning("GitHub webhook rejected — webhook secret not configured delivery=%s", delivery)
        raise HTTPException(status_code=503, detail="GitHub webhook secret not configured")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc

    payload["_github_event"] = event
    if event == "ping":
        logger.info("GitHub webhook ping delivery=%s", delivery)
        return JSONResponse({"ok": True, "status": "pong"})

    status = process_github_webhook_payload(payload, manager=manager)
    logger.info("GitHub webhook event=%s delivery=%s status=%s", event, delivery, status)
    return JSONResponse({"ok": True, "status": status})
