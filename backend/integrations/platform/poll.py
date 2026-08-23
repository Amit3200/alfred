"""Poll connector APIs without webhooks (preview or replicate)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from backend.integrations.platform.actions import apply_entity
from backend.integrations.platform.registry import get_connector
from backend.integrations.sync.store import SyncStateStore
from backend.models.config import AlfredConfig

logger = logging.getLogger(__name__)

_KIND_GETTERS = {
    "tickets": "list_tickets",
    "tasks": "list_tasks",
}


def poll_connector(
    connector_id: str,
    config: AlfredConfig,
    *,
    data_dir: Path,
    kinds: list[str] | None = None,
    replicate: bool = False,
    limit: int = 50,
) -> dict[str, Any]:
    """Fetch tickets/tasks/chats over REST. Webhook secret is not required.

    When ``replicate`` is false, returns a preview only. When true, upserts onto
    Slack Lists / JIRA using the same mapping store as webhooks.
    """
    connector = get_connector(connector_id)
    if connector is None:
        return {"ok": False, "error": f"Unknown connector `{connector_id}`."}
    if not connector.enabled(config):
        return {"ok": False, "error": f"Connector `{connector_id}` is disabled."}

    selected = [k for k in (kinds or ["tickets", "tasks"]) if k in {*_KIND_GETTERS, "chats"}]
    if not selected:
        selected = ["tickets", "tasks"]
    cap = max(1, min(int(limit or 50), 200))
    targets = connector.replica_targets(config) if replicate else ()

    preview: dict[str, Any] = {}
    applied: list[dict[str, Any]] = []
    errors: list[str] = []

    if "chats" in selected:
        try:
            chats = connector.list_chats(config)
            preview["chats"] = chats[:cap]
            preview["chat_count"] = len(preview["chats"])
        except Exception as exc:
            logger.warning("Connector poll chats failed connector=%s: %s", connector_id, exc)
            errors.append(f"chats: {exc}")

    for kind, method_name in _KIND_GETTERS.items():
        if kind not in selected:
            continue
        try:
            entities = getattr(connector, method_name)(config, limit=cap)
        except Exception as exc:
            logger.warning("Connector poll %s failed connector=%s: %s", kind, connector_id, exc)
            errors.append(f"{kind}: {exc}")
            continue
        accepted = [entity for entity in entities if connector.accepts(config, entity)]
        preview[kind] = [entity.to_dict() for entity in accepted[:cap]]
        preview[f"{kind.rstrip('s')}_count"] = len(preview[kind])
        if not replicate:
            continue
        for entity in accepted[:cap]:
            applied.append(
                apply_entity(
                    entity,
                    config,
                    data_dir=data_dir,
                    targets=targets,
                )
            )

    created = sum(
        1
        for row in applied
        if any(
            (target or {}).get("status") == "created"
            for target in (row.get("targets") or {}).values()
        )
    )
    existed = sum(
        1
        for row in applied
        if row.get("ok") and all(
            (target or {}).get("status") == "exists"
            for target in (row.get("targets") or {}).values()
        )
        and row.get("targets")
    )
    result = {
        "ok": not errors,
        "connector_id": connector_id,
        "replicate": replicate,
        "preview": preview,
        "applied": len(applied),
        "created": created,
        "already_mapped": existed,
        "results": applied if replicate else [],
        "errors": errors,
        "error": "; ".join(errors) if errors else None,
    }
    SyncStateStore(data_dir).update(
        f"connector:{connector_id}",
        {
            "replicate": replicate,
            "ticket_count": int(preview.get("ticket_count") or 0),
            "task_count": int(preview.get("task_count") or 0),
            "chat_count": int(preview.get("chat_count") or 0),
            "applied": len(applied),
            "created": created,
        },
    )
    return result
