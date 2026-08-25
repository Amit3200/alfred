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
    skipped: list[dict[str, Any]] = []
    for event in events:
        event_type = str(event.event_type or "").strip() or "unknown"
        entity = event.entity
        if entity is None:
            ignored_noise = event_type.startswith(("message.", "chat.")) and event_type not in {
                "message.ticket.attached",
                "message.flagged",
            }
            reason = "ignored_event" if ignored_noise else "unparsed_entity"
            skipped.append({"event_type": event_type, "reason": reason})
            logger.info(
                "Connector webhook skip connector=%s event_type=%s reason=%s",
                connector_id,
                event_type,
                reason,
            )
            continue
        if event.needs_enrich:
            try:
                entity = connector.enrich(config, entity, data_dir=manager.data_dir)
            except Exception:
                logger.exception("Connector enrich failed connector=%s event_type=%s", connector_id, event_type)
        if entity.action == "ignore":
            skipped.append({"event_type": event_type, "reason": "ignore_action", "id": entity.external_id})
            logger.info(
                "Connector webhook skip connector=%s event_type=%s reason=ignore_action id=%s",
                connector_id,
                event_type,
                entity.external_id,
            )
            continue
        if not connector.accepts(config, entity):
            reason = "filtered"
            reject = getattr(connector, "reject_reason", None)
            if callable(reject):
                reason = str(reject(config, entity) or reason)
            skipped.append(
                {
                    "event_type": event_type,
                    "reason": reason,
                    "id": entity.external_id,
                    "chat_id": entity.chat_id,
                    "kind": entity.kind,
                }
            )
            logger.info(
                "Connector webhook skip connector=%s event_type=%s reason=%s kind=%s id=%s chat_id=%s",
                connector_id,
                event_type,
                reason,
                entity.kind,
                entity.external_id,
                entity.chat_id or "-",
            )
            continue
        applied = apply_entity(
            entity,
            config,
            data_dir=manager.data_dir,
            targets=targets,
        )
        results.append(applied)
        slack = (applied.get("targets") or {}).get("slack_board") or {}
        jira = (applied.get("targets") or {}).get("jira") or {}
        logger.info(
            "Connector webhook applied connector=%s event_type=%s id=%s title=%s slack=%s jira=%s",
            connector_id,
            event_type,
            entity.external_id,
            (entity.title or "")[:80],
            slack.get("display_id") or slack.get("status") or slack.get("error") or "-",
            jira.get("jira_key") or jira.get("status") or jira.get("error") or "-",
        )
    logger.info(
        "Connector webhook connector=%s event_count=%s applied=%s skipped=%s event_types=%s",
        connector_id,
        len(events),
        len(results),
        len(skipped),
        ",".join(str(event.event_type or "unknown") for event in events) or "-",
    )
    return {
        "ok": True,
        "status": "processed",
        "applied": len(results),
        "skipped": skipped,
        "results": results,
    }
