"""Sync JIRA projects and Slack↔JIRA identity snapshot Alfred maintains."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from backend.integrations.identity.user_identity import build_workspace_identity_map
from backend.integrations.sync.store import SyncStateStore
from backend.models.config import AlfredConfig

logger = logging.getLogger(__name__)


def _snapshot_path(data_dir: Path | None) -> Path:
    from backend.paths import get_data_dir

    return get_data_dir(data_dir) / "jira_context_snapshot.json"


def sync_jira_context(
    config: AlfredConfig,
    *,
    data_dir: Path | None = None,
    apply_assignee_map: bool = False,
    manager: Any | None = None,
) -> dict[str, Any]:
    """Refresh JIRA project list and Slack↔JIRA identity map snapshot."""
    if not config.jira.enabled:
        return {"ok": False, "error": "JIRA integration is disabled."}

    store = SyncStateStore(data_dir)
    projects: list[dict[str, Any]] = []
    projects_error: str | None = None

    try:
        from backend.integrations.jira.api import JiraApiClient

        client = JiraApiClient.from_alfred_config(config)
        projects = client.list_projects()
    except Exception as exc:
        projects_error = str(exc)
        logger.warning("JIRA project list failed during sync: %s", exc)

    identity = build_workspace_identity_map(config, data_dir=data_dir, include_github=False)
    if identity.get("error"):
        return {"ok": False, "error": str(identity["error"]), "projects_error": projects_error}

    suggestion = dict(identity.get("assignee_map_suggestion") or {})
    snapshot = {
        "projects": projects,
        "identity_count": int(identity.get("count") or 0),
        "matched_jira": int(identity.get("matched_jira") or 0),
        "assignee_map_suggestion": suggestion,
        "project_keys": [p.get("key") for p in projects if p.get("key")],
    }
    _snapshot_path(data_dir).write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")

    merged_assignees = dict(config.jira.assignee_map)
    added = 0
    if apply_assignee_map and suggestion:
        for key, email in suggestion.items():
            if key not in merged_assignees:
                merged_assignees[key] = email
                added += 1
        if added and manager is not None:
            config.jira.assignee_map = merged_assignees
            manager.save_config(config)

    section = store.update(
        "jira_context",
        {
            "project_count": len(projects),
            "identity_count": snapshot["identity_count"],
            "matched_jira": snapshot["matched_jira"],
            "assignee_map_added": added,
        },
    )
    logger.info(
        "JIRA context sync: %d projects, %d identities (%d JIRA matches)",
        len(projects),
        snapshot["identity_count"],
        snapshot["matched_jira"],
    )
    return {
        "ok": True,
        "project_count": len(projects),
        "identity_count": snapshot["identity_count"],
        "matched_jira": snapshot["matched_jira"],
        "assignee_map_suggestion_count": len(suggestion),
        "assignee_map_added": added,
        "projects_error": projects_error,
        "last_sync_at": section.get("last_sync_at"),
        "snapshot_path": str(_snapshot_path(data_dir)),
    }


def load_jira_context_snapshot(data_dir: Path | None = None) -> dict[str, Any]:
    path = _snapshot_path(data_dir)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}
