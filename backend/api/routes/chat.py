"""Admin UI chat API — multi-session agentic chat."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from backend.api.deps import get_manager, require_admin
from backend.config_manager import ConfigManager
from backend.api.ui_chat import UIChatService
from backend.paths import exports_dir

router = APIRouter(prefix="/chat", tags=["chat"])


class CreateChatRequest(BaseModel):
    title: str = "New chat"


class SendMessageRequest(BaseModel):
    content: str = Field(min_length=1)


class ExportChatRequest(BaseModel):
    filename: str | None = None


from fastapi import Request

def _service(request: Request, manager: ConfigManager = Depends(get_manager)) -> UIChatService:
    queue = getattr(request.app.state, "queue", None)
    return UIChatService(manager, queue=queue)


@router.get("/sessions")
def list_sessions(_: ConfigManager = Depends(require_admin), service: UIChatService = Depends(_service)):
    return {"sessions": service.list_chats()}


@router.post("/sessions")
def create_session(
    body: CreateChatRequest,
    _: ConfigManager = Depends(require_admin),
    service: UIChatService = Depends(_service),
):
    return service.create_chat(title=body.title)


@router.get("/sessions/{chat_id}")
def get_session(
    chat_id: str,
    _: ConfigManager = Depends(require_admin),
    service: UIChatService = Depends(_service),
):
    chat = service.get_chat(chat_id)
    if chat is None:
        raise HTTPException(status_code=404, detail="Chat not found")
    return chat


@router.delete("/sessions/{chat_id}")
def delete_session(
    chat_id: str,
    _: ConfigManager = Depends(require_admin),
    service: UIChatService = Depends(_service),
):
    if not service.delete_chat(chat_id):
        raise HTTPException(status_code=404, detail="Chat not found")
    return {"ok": True}


@router.post("/sessions/{chat_id}/messages")
def send_message(
    chat_id: str,
    body: SendMessageRequest,
    _: ConfigManager = Depends(require_admin),
    service: UIChatService = Depends(_service),
):
    try:
        return service.send_message(chat_id, body.content)
    except KeyError:
        raise HTTPException(status_code=404, detail="Chat not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/sessions/{chat_id}/export")
def export_session(
    chat_id: str,
    body: ExportChatRequest | None = None,
    manager: ConfigManager = Depends(require_admin),
    service: UIChatService = Depends(_service),
):
    try:
        return service.export_chat(chat_id, filename=body.filename if body else None)
    except KeyError:
        raise HTTPException(status_code=404, detail="Chat not found") from None


@router.get("/exports/{filename}")
def download_export(
    filename: str,
    manager: ConfigManager = Depends(require_admin),
):
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    path = exports_dir(manager.data_dir) / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Export not found")
    return FileResponse(path, media_type="text/markdown", filename=filename)
