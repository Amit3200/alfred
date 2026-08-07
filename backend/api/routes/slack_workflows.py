"""Admin API for Slack channel workflows and List board bindings (SQLite-backed)."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.api.deps import require_admin
from backend.config_manager import ConfigManager
from backend.db.slack_workflows_db import (
    db_create_board_binding,
    db_delete_board_binding,
    db_delete_board_bindings_for_channel,
    db_delete_channel_workflow,
    db_get_board_binding,
    db_get_board_binding_for_list_id,
    db_list_board_bindings,
    db_list_channel_workflows,
    db_repair_board_bindings,
    db_update_board_binding,
    db_upsert_channel_workflow,
)
from backend.routing.slack_board_intent import is_placeholder_list_id

router = APIRouter(prefix="/slack/workflows", tags=["slack-workflows"])

TicketSystem = Literal["ask", "slack_list", "jira"]


class ChannelWorkflowPayload(BaseModel):
    channel_id: str
    channel_name: str = ""
    ticket_system: TicketSystem = "ask"
    jira_project_key: str = ""
    enabled: bool = True


class BoardBindingPayload(BaseModel):
    board_key: str = Field(min_length=1, max_length=80)
    list_id: str = Field(min_length=1)
    channel_id: str = Field(min_length=1)
    channel_name: str = ""
    list_name: str = ""
    display_id_prefix: str = "TS"
    next_display_num: int = Field(default=1, ge=1)
    default_status: str = "Not picked"
    auto_approve_writes: bool = False
    columns: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True


class BoardBindingUpdatePayload(BaseModel):
    board_key: str | None = None
    list_id: str | None = None
    channel_name: str | None = None
    list_name: str | None = None
    display_id_prefix: str | None = None
    next_display_num: int | None = Field(default=None, ge=1)
    default_status: str | None = None
    auto_approve_writes: bool | None = None
    columns: dict[str, str] | None = None
    enabled: bool | None = None


@router.get("/channels")
def list_channels(manager: ConfigManager = Depends(require_admin)) -> dict[str, Any]:
    rows = db_list_channel_workflows(manager.data_dir)
    return {"channels": rows, "total": len(rows)}


@router.put("/channels/{channel_id}")
def upsert_channel(
    channel_id: str,
    payload: ChannelWorkflowPayload,
    manager: ConfigManager = Depends(require_admin),
) -> dict[str, Any]:
    row = db_upsert_channel_workflow(
        manager.data_dir,
        channel_id=channel_id or payload.channel_id,
        channel_name=payload.channel_name,
        ticket_system=payload.ticket_system,
        jira_project_key=payload.jira_project_key,
        enabled=payload.enabled,
    )
    return {"channel": row}


@router.delete("/channels/{channel_id}")
def delete_channel(
    channel_id: str,
    manager: ConfigManager = Depends(require_admin),
) -> dict[str, Any]:
    if not db_delete_channel_workflow(manager.data_dir, channel_id):
        raise HTTPException(status_code=404, detail="Channel workflow not found")
    return {"ok": True}


@router.get("/boards")
def list_boards(manager: ConfigManager = Depends(require_admin)) -> dict[str, Any]:
    rows = db_list_board_bindings(manager.data_dir)
    return {"boards": rows, "total": len(rows)}


@router.post("/boards/dedupe")
def dedupe_boards(manager: ConfigManager = Depends(require_admin)) -> dict[str, Any]:
    """Remove duplicate channel/list bindings and apply unique indexes."""
    removed = db_repair_board_bindings(manager.data_dir)
    rows = db_list_board_bindings(manager.data_dir)
    return {"ok": True, "boards": len(rows), "duplicate_rows_removed": removed}


@router.delete("/boards/channel/{channel_id}")
def delete_boards_for_channel(
    channel_id: str,
    manager: ConfigManager = Depends(require_admin),
) -> dict[str, Any]:
    removed = db_delete_board_bindings_for_channel(manager.data_dir, channel_id)
    if removed <= 0:
        raise HTTPException(status_code=404, detail="No board bindings found for this channel")
    return {"ok": True, "removed": removed}


@router.post("/boards")
def create_board(
    payload: BoardBindingPayload,
    manager: ConfigManager = Depends(require_admin),
) -> dict[str, Any]:
    if is_placeholder_list_id(payload.list_id):
        raise HTTPException(
            status_code=400,
            detail="List id looks like a placeholder from docs/UI — use the real F… id from Slack.",
        )
    other = db_get_board_binding_for_list_id(
        manager.data_dir,
        payload.list_id,
        exclude_channel_id=payload.channel_id,
    )
    if other:
        raise HTTPException(
            status_code=409,
            detail=(
                f"List {payload.list_id} is already linked to channel "
                f"{other.get('channel_name') or other.get('channel_id')}."
            ),
        )
    try:
        row = db_create_board_binding(
            manager.data_dir,
            board_key=payload.board_key,
            list_id=payload.list_id,
            channel_id=payload.channel_id,
            channel_name=payload.channel_name,
            list_name=payload.list_name,
            display_id_prefix=payload.display_id_prefix,
            next_display_num=payload.next_display_num,
            default_status=payload.default_status,
            auto_approve_writes=payload.auto_approve_writes,
            columns=payload.columns or None,
            enabled=payload.enabled,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"board": row}


@router.get("/boards/{binding_id}")
def get_board(
    binding_id: str,
    manager: ConfigManager = Depends(require_admin),
) -> dict[str, Any]:
    row = db_get_board_binding(manager.data_dir, binding_id)
    if not row:
        raise HTTPException(status_code=404, detail="Board binding not found")
    return {"board": row}


@router.put("/boards/{binding_id}")
def update_board(
    binding_id: str,
    payload: BoardBindingUpdatePayload,
    manager: ConfigManager = Depends(require_admin),
) -> dict[str, Any]:
    existing = db_get_board_binding(manager.data_dir, binding_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Board binding not found")
    next_list_id = payload.list_id or existing["list_id"]
    if payload.list_id and is_placeholder_list_id(payload.list_id):
        raise HTTPException(
            status_code=400,
            detail="List id looks like a placeholder from docs/UI — use the real F… id from Slack.",
        )
    other = db_get_board_binding_for_list_id(
        manager.data_dir,
        next_list_id,
        exclude_channel_id=existing["channel_id"],
    )
    if other:
        raise HTTPException(
            status_code=409,
            detail=(
                f"List {next_list_id} is already linked to channel "
                f"{other.get('channel_name') or other.get('channel_id')}."
            ),
        )
    try:
        row = db_update_board_binding(
            manager.data_dir,
            binding_id,
            board_key=payload.board_key,
            list_id=payload.list_id,
            channel_name=payload.channel_name,
            list_name=payload.list_name,
            display_id_prefix=payload.display_id_prefix,
            next_display_num=payload.next_display_num,
            default_status=payload.default_status,
            auto_approve_writes=payload.auto_approve_writes,
            columns=payload.columns,
            enabled=payload.enabled,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not row:
        raise HTTPException(status_code=404, detail="Board binding not found")
    return {"board": row}


@router.delete("/boards/{binding_id}")
def delete_board(
    binding_id: str,
    manager: ConfigManager = Depends(require_admin),
) -> dict[str, Any]:
    if not db_delete_board_binding(manager.data_dir, binding_id):
        raise HTTPException(status_code=404, detail="Board binding not found")
    return {"ok": True}
