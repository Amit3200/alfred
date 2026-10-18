"""Public inbound webhook for registered connectors (Periskope, …)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from backend.integrations.platform.webhook import process_connector_webhook

router = APIRouter(prefix="/v1/connectors", tags=["connectors"])


@router.post("/{connector_id}/webhook")
async def connector_webhook(connector_id: str, request: Request) -> JSONResponse:
    manager = request.app.state.config_manager
    body = await request.body()
    headers = {key.lower(): value for key, value in request.headers.items()}
    result = process_connector_webhook(
        connector_id,
        headers=headers,
        body=body,
        manager=manager,
    )
    status = int(result.pop("status_code", 200) or 200)
    if not result.get("ok"):
        error = str(result.get("error") or "webhook_failed")
        raise HTTPException(status_code=status, detail=error)
    return JSONResponse(result)
