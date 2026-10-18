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


class ConnectorPollRequest(BaseModel):
    replicate: bool = Field(
        default=False,
        description="If true, create Slack List / JIRA items. If false, preview only.",
    )
    kinds: list[str] = Field(
        default_factory=lambda: ["tickets", "tasks"],
        description="Subset of tickets, tasks, chats.",
    )
    limit: int = Field(default=50, ge=1, le=200)


@router.get("/status")
def sync_status(manager: ConfigManager = Depends(require_admin)) -> dict[str, Any]:
    config, _ = manager.load_merged()
    store = SyncStateStore(manager.data_dir)
    snapshot = load_jira_context_snapshot(manager.data_dir)
    connectors = {
        key.removeprefix("connector:"): store.get(key)
        for key in store.status()
        if str(key).startswith("connector:")
    }
    return {
        "slack_users": store.get("slack_users"),
        "jira_context": store.get("jira_context"),
        "connectors": connectors,
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


@router.post("/connectors/{connector_id}")
def poll_connector_endpoint(
    connector_id: str,
    body: ConnectorPollRequest,
    manager: ConfigManager = Depends(require_admin),
) -> dict[str, Any]:
    from backend.integrations.platform.poll import poll_connector

    config, _ = manager.load_merged()
    return poll_connector(
        connector_id,
        config,
        data_dir=manager.data_dir,
        kinds=body.kinds,
        replicate=body.replicate,
        limit=body.limit,
    )
