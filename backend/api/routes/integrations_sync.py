"""Admin API for manual Slack/JIRA context sync."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from backend.api.deps import require_admin
from backend.config_manager import ConfigManager
from backend.integrations.sync.jira_snapshot import load_jira_context_snapshot, sync_jira_context
from backend.integrations.sync.slack_users import sync_slack_users
from backend.integrations.sync.store import SyncStateStore

router = APIRouter(prefix="/integrations/sync", tags=["integrations-sync"])


class JiraSyncRequest(BaseModel):
    apply_assignee_map: bool = Field(
        default=False,
        description="Merge new Slack↔JIRA email mappings into jira.assignee_map in config.",
    )


@router.get("/status")
def sync_status(manager: ConfigManager = Depends(require_admin)) -> dict[str, Any]:
    config, _ = manager.load_merged()
    store = SyncStateStore(manager.data_dir)
    snapshot = load_jira_context_snapshot(manager.data_dir)
    return {
        "slack_users": store.get("slack_users"),
        "jira_context": store.get("jira_context"),
        "slack_refresh_hours": float(getattr(config.slack, "user_cache_refresh_hours", 1) or 1),
        "observability_refresh_hours": float(
            getattr(config.observability, "slack_user_preload_hours", 1) or 1
        ),
        "jira_snapshot": {
            "project_count": len(snapshot.get("projects") or []),
            "identity_count": snapshot.get("identity_count"),
            "matched_jira": snapshot.get("matched_jira"),
            "assignee_suggestions": len(snapshot.get("assignee_map_suggestion") or {}),
        },
    }


@router.post("/slack/users")
def sync_slack_users_endpoint(manager: ConfigManager = Depends(require_admin)) -> dict[str, Any]:
    config, _ = manager.load_merged()
    return sync_slack_users(config, data_dir=manager.data_dir, force=True)


@router.post("/jira/context")
def sync_jira_context_endpoint(
    body: JiraSyncRequest,
    manager: ConfigManager = Depends(require_admin),
) -> dict[str, Any]:
    config, _ = manager.load_merged()
    return sync_jira_context(
        config,
        data_dir=manager.data_dir,
        apply_assignee_map=body.apply_assignee_map,
        manager=manager if body.apply_assignee_map else None,
    )
