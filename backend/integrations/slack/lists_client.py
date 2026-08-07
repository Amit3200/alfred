"""Slack Lists API wrapper."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def api_call(client: Any, method: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = client.api_call(method, json=payload)
    if not response.get("ok"):
        error = str(response.get("error") or "unknown_error")
        raise RuntimeError(f"Slack {method} failed: {error}")
    return response


def list_columns(client: Any, list_id: str) -> list[dict[str, Any]]:
    try:
        response = api_call(client, "slackLists.columns.list", {"list_id": list_id})
    except RuntimeError as exc:
        if "unknown_method" in str(exc).lower() or "not_allowed" in str(exc).lower():
            logger.warning("slackLists.columns.list unavailable: %s", exc)
            return []
        raise
    columns = response.get("columns") or response.get("schema") or []
    return list(columns) if isinstance(columns, list) else []


def get_item(client: Any, list_id: str, record_id: str) -> dict[str, Any] | None:
    response = api_call(
        client,
        "slackLists.items.info",
        {"list_id": list_id, "id": record_id},
    )
    record = response.get("record")
    return record if isinstance(record, dict) else None


def list_items(client: Any, list_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
    try:
        response = api_call(
            client,
            "slackLists.items.list",
            {"list_id": list_id, "limit": min(limit, 200)},
        )
    except RuntimeError as exc:
        logger.warning("slackLists.items.list failed: %s", exc)
        return []
    items = response.get("items") or response.get("records") or []
    return list(items) if isinstance(items, list) else []


def create_item(
    client: Any,
    list_id: str,
    initial_fields: list[dict[str, Any]],
) -> dict[str, Any]:
    response = api_call(
        client,
        "slackLists.items.create",
        {"list_id": list_id, "initial_fields": initial_fields},
    )
    record = response.get("record") or response.get("item") or {}
    return record if isinstance(record, dict) else {}


def update_cells(client: Any, list_id: str, cells: list[dict[str, Any]]) -> dict[str, Any]:
    return api_call(client, "slackLists.items.update", {"list_id": list_id, "cells": cells})
