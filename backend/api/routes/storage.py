"""Admin API for local SQLite maintenance."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.api.deps import require_admin
from backend.config_manager import ConfigManager
from backend.storage.db_maintenance import cleanup_db, get_db_stats

router = APIRouter(prefix="/storage", tags=["storage"])

DbCleanupScope = Literal["observability", "sessions", "slack_cache", "all"]


class DbCleanupRequest(BaseModel):
    scope: DbCleanupScope = Field(description="Which tables to clean")
    older_than_days: int | None = Field(
        default=None,
        ge=0,
        description="If set, only delete rows older than this many days. Omit to delete all rows in scope.",
    )
    vacuum: bool = Field(default=True, description="Run VACUUM after delete to reclaim disk space")


@router.get("/db")
def db_stats(manager: ConfigManager = Depends(require_admin)) -> dict[str, Any]:
    return get_db_stats(manager.data_dir)


@router.post("/db/cleanup")
def db_cleanup(
    body: DbCleanupRequest,
    manager: ConfigManager = Depends(require_admin),
) -> dict[str, Any]:
    try:
        return cleanup_db(
            manager.data_dir,
            scope=body.scope,
            older_than_days=body.older_than_days,
            vacuum=body.vacuum,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
