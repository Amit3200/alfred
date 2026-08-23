"""Inbound webhook dispatcher for registered connectors."""

from __future__ import annotations

import json
import logging
from typing import Any

from backend.config_manager import ConfigManager
from backend.integrations.platform.actions import apply_entity
from backend.integrations.platform.registry import get_connector

logger = logging.getLogger(__name__)


def process_connector_webhook(
    connector_id: str,
    *,
    headers: dict[str, str],
    body: bytes,
    manager: ConfigManager,
) -> dict[str, Any]:
    connector = get_connector(connector_id)
    if connector is None:
        return {"ok": False, "error": "unknown_connector", "status_code": 404}

    config, _secrets = manager.load_merged()
    if not connector.enabled(config):
        return {"ok": False, "error": "connector_disabled", "status_code": 503}

    secret = connector.webhook_secret(config)
    if not secret:
        return {"ok": False, "error": "webhook_secret_missing", "status_code": 503}
    if not connector.verify_webhook(headers=headers, body=body, secret=secret):
        return {"ok": False, "error": "invalid_signature", "status_code": 401}

    try:
        events = connector.parse_webhook(headers=headers, body=body)
    except json.JSONDecodeError:
        return {"ok": False, "error": "invalid_json", "status_code": 400}

    targets = connector.replica_targets(config)
    results: list[dict[str, Any]] = []
    for event in events:
        entity = event.entity
        if entity is None:
            continue
        if event.needs_enrich:
            try:
                entity = connector.enrich(config, entity)
            except Exception:
                logger.exception("Connector enrich failed connector=%s", connector_id)
        if entity.action == "ignore" or not connector.accepts(config, entity):
            continue
        results.append(
            apply_entity(
                entity,
                config,
                data_dir=manager.data_dir,
                targets=targets,
            )
        )
    logger.info(
        "Connector webhook connector=%s event_count=%s applied=%s",
        connector_id,
        len(events),
        len(results),
    )
    return {"ok": True, "status": "processed", "applied": len(results), "results": results}
