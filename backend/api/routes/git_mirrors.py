"""Admin API for local git repo mirrors."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.api.deps import require_admin
from backend.config_manager import ConfigManager
from backend.git.mirror import WorkspaceMirrorManager

router = APIRouter(prefix="/git/mirrors", tags=["git-mirrors"])

CleanupScope = Literal["expired", "workspaces", "shared", "all"]


class MirrorCleanupRequest(BaseModel):
    scope: CleanupScope = "expired"


class MirrorSyncRequest(BaseModel):
    repos: list[str] = Field(default_factory=list)


@router.get("/repos/available")
def list_available_repos(manager: ConfigManager = Depends(require_admin)) -> dict[str, Any]:
    """List repos from configured org (or user) plus git.repos allowlist."""
    config, _ = manager.load_merged()
    if not config.git.enabled:
        return {
            "enabled": False,
            "repos": list(config.git.repos),
            "configured": list(config.git.repos),
            "remote": [],
            "source": "disabled",
            "org": config.git.default_org or None,
            "error": "Git integration is disabled",
        }
    if not config.git.token:
        configured = list(config.git.repos)
        return {
            "enabled": True,
            "repos": configured,
            "configured": configured,
            "remote": [],
            "source": "configured",
            "org": config.git.default_org or None,
            "error": "Git token is not configured — add it under Secrets.",
        }
    from backend.git.api import GitApiClient

    try:
        payload = GitApiClient.from_alfred_config(config).list_available_repos()
    except Exception as exc:
        configured = list(config.git.repos)
        return {
            "enabled": True,
            "repos": configured,
            "configured": configured,
            "remote": [],
            "source": "configured",
            "org": config.git.default_org or None,
            "error": str(exc),
        }
    payload["enabled"] = True
    return payload


@router.get("")
def get_mirrors(manager: ConfigManager = Depends(require_admin)) -> dict[str, Any]:
    config, _ = manager.load_merged()
    if not config.git.enabled:
        return {
            "enabled": False,
            "summary": {},
            "workspaces": [],
            "shared": [],
        }
    mirror = WorkspaceMirrorManager(config.git, manager.data_dir)
    return {
        "enabled": True,
        "summary": mirror.storage_summary(),
        "workspaces": mirror.list_workspaces(),
        "shared": mirror.list_shared(),
    }


@router.post("/cleanup")
def cleanup_mirrors(
    body: MirrorCleanupRequest,
    manager: ConfigManager = Depends(require_admin),
) -> dict[str, Any]:
    config, _ = manager.load_merged()
    if not config.git.enabled:
        raise HTTPException(status_code=400, detail="Git integration is disabled")
    mirror = WorkspaceMirrorManager(config.git, manager.data_dir)
    removed_workspaces: list[str] = []
    removed_shared: list[str] = []

    if body.scope == "expired":
        removed_workspaces.extend(mirror.cleanup_expired())
    elif body.scope == "workspaces":
        removed_workspaces.extend(mirror.cleanup_all_workspaces())
    elif body.scope == "shared":
        removed_shared.extend(mirror.cleanup_shared())
    elif body.scope == "all":
        removed_workspaces.extend(mirror.cleanup_all_workspaces())
        removed_shared.extend(mirror.cleanup_shared())

    return {
        "ok": True,
        "scope": body.scope,
        "removed_workspaces": removed_workspaces,
        "removed_shared": removed_shared,
        "summary": mirror.storage_summary(),
    }


@router.delete("/workspaces/{workspace_id}")
def delete_workspace(
    workspace_id: str,
    manager: ConfigManager = Depends(require_admin),
) -> dict[str, Any]:
    config, _ = manager.load_merged()
    if not config.git.enabled:
        raise HTTPException(status_code=400, detail="Git integration is disabled")
    mirror = WorkspaceMirrorManager(config.git, manager.data_dir)
    if not mirror.drop_workspace_by_id(workspace_id):
        raise HTTPException(status_code=404, detail=f"Workspace {workspace_id!r} not found")
    return {"ok": True, "removed": workspace_id, "summary": mirror.storage_summary()}


@router.delete("/shared/{shared_id}")
def delete_shared_mirror(
    shared_id: str,
    manager: ConfigManager = Depends(require_admin),
) -> dict[str, Any]:
    config, _ = manager.load_merged()
    if not config.git.enabled:
        raise HTTPException(status_code=400, detail="Git integration is disabled")
    mirror = WorkspaceMirrorManager(config.git, manager.data_dir)
    if not mirror.drop_shared_by_id(shared_id):
        raise HTTPException(status_code=404, detail=f"Shared mirror {shared_id!r} not found")
    return {"ok": True, "removed": shared_id, "summary": mirror.storage_summary()}


@router.post("/sync")
def sync_shared_mirrors(
    body: MirrorSyncRequest,
    manager: ConfigManager = Depends(require_admin),
) -> dict[str, Any]:
    config, _ = manager.load_merged()
    if not config.git.enabled:
        raise HTTPException(status_code=400, detail="Git integration is disabled")
    if not config.git.token:
        raise HTTPException(status_code=400, detail="Git token is not configured")
    mirror = WorkspaceMirrorManager(config.git, manager.data_dir)
    results = mirror.sync_shared(body.repos or None)

    from backend.api.routes.repo_context import build_context_after_sync

    context_result = build_context_after_sync(manager, sync_results=results)
    return {
        "ok": all(item.get("ok") for item in results),
        "results": results,
        "context": context_result,
        "shared": mirror.list_shared(),
        "summary": mirror.storage_summary(),
    }
