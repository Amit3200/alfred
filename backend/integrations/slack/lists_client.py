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


def list_access_error_message(
    list_id: str,
    *,
    error_code: str = "",
    write_access: bool = False,
) -> str:
    code = (error_code or "not_found").replace("_", " ")
    if write_access:
        return (
            f"Slack List `{list_id}` is visible but Alfred cannot **create** items ({code}). "
            "Reinstalling the app or OAuth scopes alone is usually not enough — the List must "
            "grant **edit** access to Alfred:\n"
            "• Open the List in Slack → **Share** → invite **@alfred** with **Can edit**\n"
            "• Or open this channel's **Task List** tab and run `@alfred link board to F…` again\n\n"
            "If the id might be wrong, copy **F…** from the Task List tab URL "
            "(watch for similar characters like `0`/`O` and `8`/`B`)."
        )
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
) -> list[str]:
    """Best-effort grant so the bot can read/write a channel-attached List."""
    notes: list[str] = []
    lid = (list_id or "").strip()
    if not lid:
        return notes
    if not bot_user_id:
        try:
            auth = client.auth_test()
            bot_user_id = str(auth.get("user_id") or "")
        except Exception as exc:
            msg = f"Could not resolve bot user id: {exc}"
            logger.warning(msg)
            notes.append(msg)
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
            msg = f"Could not grant Alfred write access on the List ({exc})"
            logger.warning(msg)
            notes.append(msg)
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
            msg = f"Could not grant this channel write access on the List ({exc})"
            logger.warning(msg)
            notes.append(msg)
    return notes


def alfred_board_list_schema(*, include_display_id: bool = True) -> list[dict[str, Any]]:
    """Standard Alfred task board schema for slackLists.create."""
    schema: list[dict[str, Any]] = [
        {
            "key": "name",
            "name": "Name",
            "type": "text",
            "is_primary_column": True,
        },
        {
            "key": "status",
            "name": "Status",
            "type": "select",
            "options": {
                "format": "single_select",
                "choices": [
                    {"value": "not_picked", "label": "Not picked", "color": "gray"},
                    {"value": "in_progress", "label": "In progress", "color": "yellow"},
                    {"value": "review", "label": "Review", "color": "blue"},
                    {"value": "done", "label": "Done", "color": "green"},
                ],
            },
        },
        {
            "key": "ticket_details",
            "name": "Ticket Details",
            "type": "text",
        },
        {
            "key": "severity",
            "name": "Severity",
            "type": "select",
            "options": {
                "format": "single_select",
                "choices": [
                    {"value": "high", "label": "High", "color": "red"},
                    {"value": "medium", "label": "Medium", "color": "yellow"},
                    {"value": "low", "label": "Low", "color": "green"},
                ],
            },
        },
        {
            "key": "assignee",
            "name": "Assignee",
            "type": "user",
            "options": {"format": "single_entity"},
        },
        {
            "key": "merchant_name",
            "name": "Merchant Name",
            "type": "text",
        },
        {
            "key": "merchant_domain",
            "name": "Merchant Domain",
            "type": "text",
        },
    ]
    if include_display_id:
        schema.append(
            {
                "key": "display_id",
                "name": "Display ID",
                "type": "text",
            }
        )
    return schema


ALFRED_BOARD_COLUMN_MAP: dict[str, str] = {
    "title": "Name",
    "status": "Status",
    "severity": "Severity",
    "assignee": "Assignee",
    "merchant": "Merchant Name",
    "merchant_domain": "Merchant Domain",
    "details": "Ticket Details",
    "display_id": "Display ID",
}


def create_list(
    client: Any,
    *,
    name: str,
    description: str = "",
    schema: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Create a Slack List via slackLists.create. Returns list_id and metadata."""
    list_name = (name or "").strip()
    if not list_name:
        raise ValueError("List name is required.")
    payload: dict[str, Any] = {"name": list_name[:80]}
    desc = (description or "").strip()
    if desc:
        payload["description_blocks"] = [
            {
                "type": "rich_text",
                "elements": [
                    {
                        "type": "rich_text_section",
                        "elements": [{"type": "text", "text": desc[:500]}],
                    }
                ],
            }
        ]
    payload["schema"] = schema or alfred_board_list_schema()
    response = api_call(client, "slackLists.create", payload)
    list_id = str(response.get("list_id") or "")
    if not list_id:
        raise RuntimeError("slackLists.create succeeded but returned no list_id.")
    return {
        "list_id": list_id,
        "list_metadata": response.get("list_metadata") or {},
    }


def provision_alfred_board_list(
    client: Any,
    *,
    channel_id: str,
    list_name: str,
    description: str = "Task board managed by Alfred.",
) -> tuple[str, list[str]]:
    """Create a List Alfred owns, grant access, and verify create works."""
    created = create_list(
        client,
        name=list_name,
        description=description,
        schema=alfred_board_list_schema(include_display_id=True),
    )
    list_id = created["list_id"]
    grant_notes = grant_list_access(client, list_id, channel_id=channel_id)
    ok, verify_msg = verify_list_id(client, list_id, channel_id=channel_id)
    if not ok:
        raise SlackListAccessError(verify_msg)
    return list_id, grant_notes


def _title_probe_field(column: dict[str, Any]) -> dict[str, Any]:
    col_id = str(column.get("id") or "")
    return {
        "column_id": col_id,
        "rich_text": [
            {
                "type": "rich_text",
                "elements": [
                    {
                        "type": "rich_text_section",
                        "elements": [{"type": "text", "text": "Alfred link verify"}],
                    }
                ],
            }
        ],
    }


def delete_item(client: Any, list_id: str, record_id: str) -> None:
    api_call(
        client,
        "slackLists.items.delete",
        {"list_id": list_id, "id": record_id},
    )


def probe_list_write_access(
    client: Any,
    list_id: str,
    title_column: dict[str, Any],
) -> None:
    """Create and delete a probe item; raises SlackListAccessError if write fails."""
    field = _title_probe_field(title_column)
    record = create_item(client, list_id, [field])
    record_id = str(record.get("id") or record.get("record_id") or "")
    if not record_id:
        raise SlackListAccessError(
            list_access_error_message(list_id, error_code="create_empty", write_access=True)
        )
    try:
        delete_item(client, list_id, record_id)
    except RuntimeError as exc:
        logger.warning(
            "List write probe created item %s on %s but delete failed: %s",
            record_id,
            list_id,
            exc,
        )


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
    grant_notes = grant_list_access(client, lid, channel_id=channel_id)
    try:
        schema = list_columns(client, lid)
    except SlackListAccessError as exc:
        return False, _append_grant_notes(str(exc), grant_notes)
    if not schema:
        return False, _append_grant_notes(
            list_access_error_message(lid, error_code="schema_empty"),
            grant_notes,
        )
    title_col = next(
        (col for col in schema if isinstance(col, dict) and col.get("is_primary_column")),
        schema[0] if schema else None,
    )
    if not title_col or not str(title_col.get("id") or ""):
        return False, _append_grant_notes(
            (
                f"Slack List `{lid}` has no writable title column. "
                "Check the List schema in Slack."
            ),
            grant_notes,
        )
    try:
        probe_list_write_access(client, lid, title_col)
    except SlackListAccessError as exc:
        return False, _append_grant_notes(str(exc), grant_notes)
    return True, ""


def _append_grant_notes(message: str, grant_notes: list[str]) -> str:
    if not grant_notes:
        return message
    extra = "\n".join(f"- {note}" for note in grant_notes)
    return f"{message}\n\nAccess grant notes:\n{extra}"


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
            raise SlackListAccessError(
                list_access_error_message(list_id, error_code=code, write_access=True)
            ) from exc
        raise
    record = response.get("record") or response.get("item") or {}
    return record if isinstance(record, dict) else {}


def update_cells(client: Any, list_id: str, cells: list[dict[str, Any]]) -> dict[str, Any]:
    return api_call(client, "slackLists.items.update", {"list_id": list_id, "cells": cells})
