"""Slack Lists API wrapper."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class SlackListAccessError(RuntimeError):
    """Raised when a List id cannot be read or written by the bot."""


def _slack_error_code(exc: BaseException) -> str:
    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        return str(response.get("error") or "")
    text = str(exc)
    if "list_not_found" in text:
        return "list_not_found"
    if "file_not_found" in text:
        return "file_not_found"
    return ""


def list_access_error_message(list_id: str, *, error_code: str = "") -> str:
    code = (error_code or "not_found").replace("_", " ")
    return (
        f"Slack List `{list_id}` is not accessible ({code}). "
        "Copy the **F…** id from the Task List tab URL while viewing the list in Slack "
        "(watch for similar characters like `0`/`O` and `8`/`B`). "
        f"Then run `@alfred link board to F…` or re-save in **Settings → Slack boards**. "
        "Ensure Alfred has `lists:read` / `lists:write`, is **invited to the channel**, "
        "and the Slack app was reinstalled after adding those scopes."
    )


def api_call(client: Any, method: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Call a Slack Web API method (JSON body for Lists APIs)."""
    try:
        response = client.api_call(method, json=payload)
    except Exception as exc:
        from slack_sdk.errors import SlackApiError

        if isinstance(exc, SlackApiError):
            error = _slack_error_code(exc) or str(exc)
            raise RuntimeError(f"Slack {method} failed: {error}") from exc
        raise
    if not response.get("ok"):
        error = str(response.get("error") or "unknown_error")
        raise RuntimeError(f"Slack {method} failed: {error}")
    return response


def _files_info(client: Any, file_id: str) -> dict[str, Any]:
    """files.info must use query params (GET), not JSON — unlike slackLists.* methods."""
    lid = (file_id or "").strip()
    try:
        if hasattr(client, "files_info"):
            response = client.files_info(file=lid)
        else:
            response = client.api_call("files.info", params={"file": lid})
    except Exception as exc:
        from slack_sdk.errors import SlackApiError

        if isinstance(exc, SlackApiError):
            error = _slack_error_code(exc) or str(exc)
            raise RuntimeError(f"Slack files.info failed: {error}") from exc
        raise
    if not response.get("ok"):
        error = str(response.get("error") or "unknown_error")
        raise RuntimeError(f"Slack files.info failed: {error}")
    return response


def _list_api_reachable(client: Any, list_id: str) -> bool:
    """Best-effort check that slackLists.* calls work for this list id."""
    try:
        api_call(client, "slackLists.items.list", {"list_id": list_id, "limit": 1})
        return True
    except RuntimeError:
        return False


def _schema_from_list_metadata(list_obj: dict[str, Any]) -> list[dict[str, Any]]:
    meta = list_obj.get("list_metadata") or {}
    schema = meta.get("schema") or []
    return list(schema) if isinstance(schema, list) else []


def _record_id_from_item(item: dict[str, Any]) -> str:
    return str(item.get("id") or item.get("record_id") or "")


def grant_list_access(
    client: Any,
    list_id: str,
    *,
    channel_id: str = "",
    bot_user_id: str = "",
) -> None:
    """Best-effort grant so the bot can read/write a channel-attached List."""
    lid = (list_id or "").strip()
    if not lid:
        return
    if not bot_user_id:
        try:
            auth = client.auth_test()
            bot_user_id = str(auth.get("user_id") or "")
        except Exception as exc:
            logger.warning("auth_test failed while granting list access: %s", exc)
    if bot_user_id:
        try:
            api_call(
                client,
                "slackLists.access.set",
                {
                    "list_id": lid,
                    "access_level": "write",
                    "user_ids": [bot_user_id],
                },
            )
        except RuntimeError as exc:
            logger.warning("slackLists.access.set for bot user failed: %s", exc)
    cid = (channel_id or "").strip()
    if cid:
        try:
            api_call(
                client,
                "slackLists.access.set",
                {
                    "list_id": lid,
                    "access_level": "write",
                    "channel_ids": [cid],
                },
            )
        except RuntimeError as exc:
            logger.warning("slackLists.access.set for channel failed: %s", exc)


def verify_list_id(
    client: Any,
    list_id: str,
    *,
    channel_id: str = "",
) -> tuple[bool, str]:
    """Check that list_id refers to a List the bot can read and write."""
    lid = (list_id or "").strip()
    if not lid.startswith("F"):
        return False, f"List id must start with F (got `{lid}`)."
    grant_list_access(client, lid, channel_id=channel_id)
    try:
        schema = list_columns(client, lid)
    except SlackListAccessError as exc:
        return False, str(exc)
    if not schema:
        return False, list_access_error_message(lid, error_code="schema_empty")
    title_col = next(
        (col for col in schema if isinstance(col, dict) and col.get("is_primary_column")),
        schema[0] if schema else None,
    )
    if not title_col or not str(title_col.get("id") or ""):
        return False, (
            f"Slack List `{lid}` has no writable title column. "
            "Check the List schema in Slack."
        )
    return True, ""


def list_columns(client: Any, list_id: str) -> list[dict[str, Any]]:
    """Load List column schema.

    Slack removed ``slackLists.columns.list``; schema is returned on ``files.info``
    and ``slackLists.items.info``.
    """
    try:
        response = _files_info(client, list_id)
        schema = _schema_from_list_metadata(response.get("file") or {})
        if schema:
            return schema
    except RuntimeError as exc:
        code = _slack_error_code(exc)
        if code in ("list_not_found", "file_not_found") and not _list_api_reachable(client, list_id):
            raise SlackListAccessError(list_access_error_message(list_id, error_code=code)) from exc
        logger.warning("files.info schema fetch failed: %s", exc)

    items = list_items(client, list_id, limit=1)
    for item in items:
        record_id = _record_id_from_item(item)
        if not record_id:
            continue
        try:
            response = api_call(
                client,
                "slackLists.items.info",
                {"list_id": list_id, "id": record_id},
            )
        except RuntimeError as exc:
            logger.warning("slackLists.items.info schema fetch failed: %s", exc)
            continue
        schema = _schema_from_list_metadata(response.get("list") or {})
        if schema:
            return schema

    raise SlackListAccessError(list_access_error_message(list_id))


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
        code = _slack_error_code(exc)
        if code in ("list_not_found", "file_not_found"):
            raise SlackListAccessError(list_access_error_message(list_id, error_code=code)) from exc
        logger.warning("slackLists.items.list failed: %s", exc)
        return []
    items = response.get("items") or response.get("records") or []
    return list(items) if isinstance(items, list) else []


def create_item(
    client: Any,
    list_id: str,
    initial_fields: list[dict[str, Any]],
) -> dict[str, Any]:
    try:
        response = api_call(
            client,
            "slackLists.items.create",
            {"list_id": list_id, "initial_fields": initial_fields},
        )
    except RuntimeError as exc:
        code = _slack_error_code(exc)
        if code in ("list_not_found", "file_not_found"):
            raise SlackListAccessError(list_access_error_message(list_id, error_code=code)) from exc
        raise
    record = response.get("record") or response.get("item") or {}
    return record if isinstance(record, dict) else {}


def update_cells(client: Any, list_id: str, cells: list[dict[str, Any]]) -> dict[str, Any]:
    return api_call(client, "slackLists.items.update", {"list_id": list_id, "cells": cells})
