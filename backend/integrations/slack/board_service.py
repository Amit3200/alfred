"""Resolve Slack boards and perform list CRUD."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from backend.db.slack_board_store import SlackBoardStore
from backend.formatting.slack_lists import format_list_record, list_record_to_field_map
from backend.integrations.slack.lists_client import (
    create_item,
    get_item,
    grant_list_access,
    list_columns,
    list_items,
    update_cells,
    confirm_item_visible,
    SlackListAccessError,
    _record_id_from_item,
)
from backend.models.config import AlfredConfig, SlackBoardProfile
from backend.models.task import Task

logger = logging.getLogger(__name__)


def board_enabled(config: AlfredConfig, data_dir: Path | None = None) -> bool:
    from backend.integrations.slack.workflow_registry import board_feature_enabled

    return board_feature_enabled(config, data_dir)


def resolve_board_for_task(
    config: AlfredConfig,
    task: Task,
    *,
    data_dir: Path | None = None,
) -> SlackBoardProfile | None:
    from backend.integrations.slack.workflow_registry import resolve_board_for_task as _resolve

    return _resolve(config, task, data_dir=data_dir)


def resolve_board_any_channel(
    config: AlfredConfig,
    *,
    channel_id: str = "",
    board_name: str = "",
    data_dir: Path | None = None,
) -> SlackBoardProfile | None:
    from backend.integrations.slack.workflow_registry import resolve_board_by_key

    if board_name:
        return resolve_board_by_key(
            config,
            board_name,
            channel_id=channel_id,
            data_dir=data_dir,
        )
    if channel_id:
        from backend.integrations.slack.workflow_registry import resolve_board_for_channel

        return resolve_board_for_channel(config, channel_id, data_dir=data_dir)
    return None


def _column_by_name(schema: list[dict[str, Any]], label: str) -> dict[str, Any] | None:
    target = (label or "").strip().lower()
    if not target:
        return None
    for col in schema:
        if not isinstance(col, dict):
            continue
        name = str(col.get("name") or "").strip().lower()
        key = str(col.get("key") or "").strip().lower()
        if name == target or key == target:
            return col
    return None


def _primary_column(schema: list[dict[str, Any]]) -> dict[str, Any] | None:
    for col in schema:
        if isinstance(col, dict) and col.get("is_primary_column"):
            return col
    return None


def _resolve_title_column(
    schema: list[dict[str, Any]],
    configured_label: str,
) -> dict[str, Any] | None:
    for label in (configured_label, "Name", "Title", "name", "title"):
        if not label:
            continue
        col = _column_by_name(schema, label)
        if col:
            return col
    return _primary_column(schema)


def load_schema(
    client: Any,
    list_id: str,
    store: SlackBoardStore,
) -> list[dict[str, Any]]:
    cached = store.get_schema_cache(list_id)
    if cached:
        return cached
    schema = list_columns(client, list_id)
    if schema:
        store.set_schema_cache(list_id, schema)
    return schema


def _select_value_for_label(column: dict[str, Any], label: str) -> str | None:
    choices = ((column.get("options") or {}).get("choices") or [])
    target = (label or "").strip().lower()
    for choice in choices:
        if not isinstance(choice, dict):
            continue
        if str(choice.get("label") or "").strip().lower() == target:
            return str(choice.get("value") or "")
    return None


def _rich_text_blocks(value: str) -> list[dict[str, Any]]:
    return [
        {
            "type": "rich_text",
            "elements": [
                {
                    "type": "rich_text_section",
                    "elements": [{"type": "text", "text": value}],
                }
            ],
        }
    ]


def _field_payload(
    column: dict[str, Any],
    value: str,
    *,
    user_ids: list[str] | None = None,
) -> dict[str, Any] | None:
    col_id = str(column.get("id") or "")
    if not col_id:
        return None
    col_type = str(column.get("type") or "text")
    payload: dict[str, Any] = {"column_id": col_id}
    if col_type in ("user", "assignee"):
        if not user_ids:
            return None
        payload["user"] = user_ids
        return payload
    if col_type in ("select", "multi_select"):
        selected = _select_value_for_label(column, value)
        if not selected:
            return None
        payload["select"] = [selected]
        return payload
    if not (value or "").strip():
        return None
    # Slack List writes reject plain `text` in requests; use rich_text blocks.
    payload["rich_text"] = _rich_text_blocks(value.strip())
    return payload


def _append_field(
    initial_fields: list[dict[str, Any]],
    column: dict[str, Any] | None,
    value: str,
    *,
    user_ids: list[str] | None = None,
) -> None:
    if not column:
        return
    field = _field_payload(column, value, user_ids=user_ids)
    if field:
        initial_fields.append(field)


def create_board_task(
    client: Any,
    config: AlfredConfig,
    store: SlackBoardStore,
    board: SlackBoardProfile,
    *,
    title: str,
    description: str = "",
    severity: str = "",
    merchant: str = "",
    assignee_user_id: str = "",
    channel_id: str = "",
    thread_ts: str = "",
) -> dict[str, Any]:
    list_id = (board.list_id or "").strip()
    if not list_id:
        raise RuntimeError("Board has no List id — run `@alfred setup board` or `@alfred link board to F…`.")

    channel = (channel_id or (board.channel_ids[0] if board.channel_ids else "")).strip()
    grant_list_access(client, list_id, channel_id=channel)
    store.clear_schema_cache(list_id)

    try:
        schema = list_columns(client, list_id)
    except SlackListAccessError as exc:
        raise RuntimeError(str(exc)) from exc
    if not schema:
        raise RuntimeError(
            "Could not load Slack List columns. Add lists:read scope and reinstall the Slack app."
        )
    store.set_schema_cache(list_id, schema)

    cols = board.columns
    initial_fields: list[dict[str, Any]] = []

    title_col = _resolve_title_column(schema, cols.title or "Name")
    _append_field(initial_fields, title_col, title.strip())

    details_col = _column_by_name(schema, cols.details or "Ticket Details")
    _append_field(initial_fields, details_col, description.strip())

    if severity.strip():
        sev_col = _column_by_name(schema, cols.severity or "Severity")
        _append_field(initial_fields, sev_col, severity.strip())

    if merchant.strip():
        merch_col = _column_by_name(schema, cols.merchant or "Merchant Name")
        _append_field(initial_fields, merch_col, merchant.strip())

    status_col = _column_by_name(schema, cols.status or "Status")
    _append_field(initial_fields, status_col, board.default_status or "Not picked")

    display_id = ""
    display_col = None
    if cols.display_id:
        display_col = _column_by_name(schema, cols.display_id)
        if display_col:
            if not channel:
                raise RuntimeError("Cannot allocate display id without a channel binding.")
            display_id = store.peek_display_id(
                channel_id=channel,
                prefix=board.display_id_prefix or "TS",
            )
            _append_field(initial_fields, display_col, display_id)

    if assignee_user_id.strip():
        assign_col = _column_by_name(schema, cols.assignee or "Assignee")
        _append_field(
            initial_fields,
            assign_col,
            "",
            user_ids=[assignee_user_id.strip()],
        )

    if not initial_fields:
        raise RuntimeError("No list columns matched — check board column mapping in config.")

    logger.info(
        "Creating Slack List item on %s with %d field(s) title=%r",
        list_id,
        len(initial_fields),
        title.strip(),
    )
    record = create_item(client, list_id, initial_fields)
    record_id = str(record.get("id") or record.get("record_id") or "")
    if not record_id:
        raise RuntimeError("Slack List create succeeded but returned no record id.")

    if not confirm_item_visible(client, list_id, record_id):
        raise RuntimeError(
            f"Slack accepted record `{record_id}` but it is not visible in List `{list_id}`. "
            "Your channel List tab may show a **different** List — run `@alfred show board config`, "
            "open the linked List URL from that reply, or `@alfred link board to F…` using the id "
            "from your channel tab URL."
        )

    if display_id:
        store.next_display_id(
            channel_id=channel,
            prefix=board.display_id_prefix or "TS",
        )

    store.register_record(
        record_id,
        board_key=board.name,
        list_id=list_id,
        channel_id=channel_id,
        display_id=display_id,
        thread_ts=thread_ts,
        title=title.strip(),
    )

    return {
        "record_id": record_id,
        "display_id": display_id,
        "list_id": list_id,
        "board": board.name,
        "title": title.strip(),
        "status": board.default_status,
        "url_hint": f"lists/{list_id}?record_id={record_id}",
    }


def update_board_task(
    client: Any,
    config: AlfredConfig,
    store: SlackBoardStore,
    *,
    ticket_ref: str,
    status: str = "",
    assignee_user_id: str = "",
    severity: str = "",
    channel_id: str = "",
) -> dict[str, Any]:
    resolved = store.resolve_record(ticket_ref)
    if resolved:
        record_id, meta = resolved
        list_id = str(meta.get("list_id") or "")
        board = resolve_board_any_channel(
            config,
            channel_id=str(meta.get("channel_id") or channel_id),
            board_name=str(meta.get("board_key") or ""),
        )
    else:
        board = resolve_board_for_task(
            config,
            Task(source="slack", user_id="", channel_id=channel_id, raw_text="", cleaned_intent=""),
        )
        list_id = board.list_id if board else ""
        record_id = ticket_ref if ticket_ref.startswith("Rec") else ticket_ref

    if not board or not list_id or not record_id:
        raise RuntimeError(f"Unknown ticket `{ticket_ref}` — register the board or use a valid ticket id.")

    grant_list_access(
        client,
        list_id,
        channel_id=channel_id or (board.channel_ids[0] if board.channel_ids else ""),
    )
    schema = load_schema(client, list_id, store)
    cells_list: list[dict[str, Any]] = []

    if status.strip():
        col = _column_by_name(schema, board.columns.status or "Status")
        field = _field_payload(col, status.strip()) if col else None
        if field:
            cells_list.append({"row_id": record_id, **field})

    if assignee_user_id.strip():
        col = _column_by_name(schema, board.columns.assignee or "Assignee")
        field = (
            _field_payload(col, "", user_ids=[assignee_user_id.strip()]) if col else None
        )
        if field:
            cells_list.append({"row_id": record_id, **field})

    if severity.strip():
        col = _column_by_name(schema, board.columns.severity or "Severity")
        field = _field_payload(col, severity.strip()) if col else None
        if field:
            cells_list.append({"row_id": record_id, **field})

    if not cells_list:
        raise RuntimeError("Nothing to update — provide status, assignee, or severity.")

    update_cells(client, list_id, cells_list)
    return {
        "record_id": record_id,
        "list_id": list_id,
        "updated": {
            k: v
            for k, v in {
                "status": status,
                "assignee_user_id": assignee_user_id,
                "severity": severity,
            }.items()
            if v
        },
    }


def get_board_task(
    client: Any,
    config: AlfredConfig,
    store: SlackBoardStore,
    ticket_ref: str,
) -> dict[str, Any]:
    resolved = store.resolve_record(ticket_ref)
    if resolved:
        record_id, meta = resolved
        list_id = str(meta.get("list_id") or "")
    else:
        record_id = ticket_ref if ticket_ref.startswith("Rec") else ""
        list_id = ""
        meta = {}
        if board_enabled(config):
            for board in config.slack.board_workflows.boards:
                if board.list_id:
                    list_id = board.list_id
                    break
    if not list_id or not record_id:
        raise RuntimeError(f"Ticket `{ticket_ref}` not found in board registry.")
    record = get_item(client, list_id, record_id)
    if not record:
        raise RuntimeError(f"Ticket `{ticket_ref}` not found in list.")
    schema = load_schema(client, list_id, store)
    return {
        "record_id": record_id,
        "display_id": str(meta.get("display_id") or ""),
        "formatted": format_list_record(record, schema=schema),
        "fields": list_record_to_field_map(record, schema=schema),
    }


def search_board_tasks(
    client: Any,
    config: AlfredConfig,
    store: SlackBoardStore,
    board: SlackBoardProfile,
    *,
    query: str = "",
    status: str = "",
    limit: int = 20,
) -> list[dict[str, Any]]:
    list_id = board.list_id
    schema = load_schema(client, list_id, store)
    items = list_items(client, list_id, limit=limit)
    results: list[dict[str, Any]] = []
    q = (query or "").strip().lower()
    status_filter = (status or "").strip().lower()

    for item in items:
        record_id = str(item.get("id") or item.get("record_id") or "")
        fields = list_record_to_field_map(item, schema=schema)
        title = fields.get("Name") or fields.get("Title") or fields.get("name") or ""
        item_status = fields.get("Status") or fields.get("status") or ""
        if status_filter and status_filter not in item_status.lower():
            continue
        blob = " ".join(fields.values()).lower()
        if q and q not in blob and q not in title.lower():
            meta = store.find_record(record_id)
            if not meta or q not in str(meta.get("display_id") or "").lower():
                continue
        meta = store.find_record(record_id)
        results.append(
            {
                "record_id": record_id,
                "display_id": (meta or {}).get("display_id") or "",
                "title": title,
                "status": item_status,
                "fields": fields,
            }
        )
    return results[:limit]


def post_ticket_comment(
    client: Any,
    store: SlackBoardStore,
    *,
    ticket_ref: str,
    text: str,
    fallback_channel: str = "",
    fallback_thread: str = "",
) -> dict[str, Any]:
    meta = store.find_record(ticket_ref) or {}
    channel = str(meta.get("channel_id") or fallback_channel or "")
    thread = str(meta.get("thread_ts") or fallback_thread or "")
    if not channel or not thread:
        raise RuntimeError("No Slack thread linked to this ticket — comment in the ticket thread.")
    response = client.chat_postMessage(channel=channel, thread_ts=thread, text=text.strip())
    return {"ok": bool(response.get("ok")), "ts": str(response.get("ts") or "")}
