"""Slack List board CRUD — domain verbs over Lists HTTP + local registry."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from backend.db.slack_board_store import SlackBoardStore
from backend.domains.slack_board.formatting import DEFAULT_BOARD_SEVERITY, normalize_board_severity
from backend.formatting.slack_lists import format_list_record, list_record_to_field_map
from backend.integrations.slack.list_fields import (
    append_field,
    column_by_name,
    field_payload,
    load_schema,
    resolve_display_id_column,
    resolve_severity_column,
    resolve_title_column,
)
from backend.integrations.slack.lists_client import (
    SlackListAccessError,
    _record_id_from_item,
    confirm_item_visible,
    create_item,
    get_item,
    grant_list_access,
    list_columns,
    list_items,
    update_cells,
)
from backend.integrations.slack.workflow_registry import (
    board_feature_enabled,
    resolve_board_by_key,
    resolve_board_for_channel,
    resolve_board_for_task as _resolve_board_for_task,
)
from backend.models.config import AlfredConfig, SlackBoardProfile
from backend.models.task import Task

logger = logging.getLogger(__name__)


def board_enabled(config: AlfredConfig, data_dir: Path | None = None) -> bool:
    return board_feature_enabled(config, data_dir)


def resolve_board_for_task(
    config: AlfredConfig,
    task: Task,
    *,
    data_dir: Path | None = None,
) -> SlackBoardProfile | None:
    return _resolve_board_for_task(config, task, data_dir=data_dir)


def resolve_board_any_channel(
    config: AlfredConfig,
    *,
    channel_id: str = "",
    board_name: str = "",
    data_dir: Path | None = None,
) -> SlackBoardProfile | None:
    if board_name:
        return resolve_board_by_key(
            config,
            board_name,
            channel_id=channel_id,
            data_dir=data_dir,
        )
    if channel_id:
        return resolve_board_for_channel(config, channel_id, data_dir=data_dir)
    return None


def _find_record_in_list(
    client: Any,
    store: SlackBoardStore,
    board: SlackBoardProfile,
    ticket_ref: str,
    *,
    channel_id: str = "",
) -> tuple[str, dict[str, Any]] | None:
    """Look up a List row by display id or Rec id when the local registry misses it."""
    ref = (ticket_ref or "").strip()
    list_id = (board.list_id or "").strip()
    if not ref or not list_id:
        return None

    schema = load_schema(client, list_id, store)
    display_col_name = board.columns.display_id or "Display ID"

    if ref.startswith("Rec"):
        record = get_item(client, list_id, ref)
        if not record:
            return None
        fields = list_record_to_field_map(record, schema=schema)
        display_id = fields.get(display_col_name) or fields.get("Display ID") or ""
        title = fields.get("Name") or fields.get("Title") or ""
        meta = {
            "board_key": board.name,
            "list_id": list_id,
            "channel_id": channel_id,
            "display_id": display_id,
            "title": title,
        }
        store.register_record(
            ref,
            board_key=board.name,
            list_id=list_id,
            channel_id=channel_id,
            display_id=display_id,
            title=title,
        )
        return ref, meta

    target = ref.upper()
    for item in list_items(client, list_id, limit=200):
        record_id = _record_id_from_item(item)
        if not record_id:
            continue
        fields = list_record_to_field_map(item, schema=schema)
        display = (fields.get(display_col_name) or fields.get("Display ID") or "").strip()
        if display.upper() != target:
            continue
        title = fields.get("Name") or fields.get("Title") or ""
        meta = {
            "board_key": board.name,
            "list_id": list_id,
            "channel_id": channel_id,
            "display_id": display,
            "title": title,
        }
        store.register_record(
            record_id,
            board_key=board.name,
            list_id=list_id,
            channel_id=channel_id,
            display_id=display,
            title=title,
        )
        logger.info("Resolved board task %s -> %s via List scan on %s", ref, record_id, list_id)
        return record_id, meta
    return None


def _resolve_board_record(
    client: Any,
    config: AlfredConfig,
    store: SlackBoardStore,
    board: SlackBoardProfile,
    ticket_ref: str,
    *,
    channel_id: str = "",
    record_id_hint: str = "",
) -> tuple[str, dict[str, Any], SlackBoardProfile]:
    """Resolve record id for updates: registry, session hint, then List scan."""
    resolved = store.resolve_record(ticket_ref)
    if resolved:
        record_id, meta = resolved
        bound = resolve_board_any_channel(
            config,
            channel_id=str(meta.get("channel_id") or channel_id),
            board_name=str(meta.get("board_key") or board.name),
        )
        return record_id, meta, bound or board

    hint = (record_id_hint or "").strip()
    if hint.startswith("Rec"):
        found = _find_record_in_list(
            client,
            store,
            board,
            hint,
            channel_id=channel_id,
        )
        if found:
            record_id, meta = found
            return record_id, meta, board

    found = _find_record_in_list(
        client,
        store,
        board,
        ticket_ref,
        channel_id=channel_id,
    )
    if found:
        record_id, meta = found
        return record_id, meta, board

    raise RuntimeError(
        f"Unknown ticket `{ticket_ref}` — not in Alfred's registry or List `{board.list_id}`. "
        "Run `@alfred show board config` to confirm the linked List."
    )


def _repair_binding_column_map(data_dir: Path | None, channel_id: str) -> None:
    """Ensure linked channels have Display ID and other column labels in the binding."""
    if not data_dir or not channel_id:
        return
    from backend.db.slack_workflows_db import db_get_board_binding_for_channel, db_update_board_binding
    from backend.integrations.slack.lists_client import ALFRED_BOARD_COLUMN_MAP

    binding = db_get_board_binding_for_channel(data_dir, channel_id)
    if not binding:
        return
    existing = dict(binding.get("columns") or {})
    merged = dict(ALFRED_BOARD_COLUMN_MAP)
    merged.update({k: v for k, v in existing.items() if v})
    if merged != existing:
        db_update_board_binding(data_dir, str(binding["id"]), columns=merged)


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
    _repair_binding_column_map(
        store._path.parent if hasattr(store, "_path") else None,
        channel,
    )

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

    title_col = resolve_title_column(schema, cols.title or "Name")
    append_field(initial_fields, title_col, title.strip())

    details_col = column_by_name(schema, cols.details or "Ticket Details")
    append_field(initial_fields, details_col, description.strip())

    sev_col = resolve_severity_column(schema, cols)
    normalized_severity = (
        normalize_board_severity(severity) if severity.strip() else DEFAULT_BOARD_SEVERITY
    )
    if sev_col and normalized_severity:
        append_field(initial_fields, sev_col, normalized_severity)

    if merchant.strip():
        merch_col = column_by_name(schema, cols.merchant or "Merchant Name")
        append_field(initial_fields, merch_col, merchant.strip())

    status_col = column_by_name(schema, cols.status or "Status")
    append_field(initial_fields, status_col, board.default_status or "Not picked")

    display_id = ""
    display_col = resolve_display_id_column(schema, cols)
    if display_col:
        if not channel:
            raise RuntimeError("Cannot allocate display id without a channel binding.")
        prefix = (board.display_id_prefix or "TS").strip()
        display_id = store.peek_display_id(channel_id=channel, prefix=prefix)
        if display_id:
            append_field(initial_fields, display_col, display_id)
            logger.info(
                "Allocated display id %s for channel %s (prefix %s)",
                display_id,
                channel,
                prefix,
            )
        else:
            logger.warning("Could not peek display id for channel %s prefix %s", channel, prefix)

    if assignee_user_id.strip():
        assign_col = column_by_name(schema, cols.assignee or "Assignee")
        append_field(
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
    record_id_hint: str = "",
) -> dict[str, Any]:
    data_dir = None
    store_path = getattr(store, "_path", None)
    if store_path is not None:
        data_dir = store_path.parent

    board = resolve_board_for_task(
        config,
        Task(source="slack", user_id="", channel_id=channel_id, raw_text="", cleaned_intent=""),
        data_dir=data_dir,
    )
    if board is None:
        board = resolve_board_any_channel(config, channel_id=channel_id)
    if board is None or not (board.list_id or "").strip():
        raise RuntimeError(
            f"Unknown ticket `{ticket_ref}` — no Slack List board linked to this channel."
        )

    record_id, _meta, board = _resolve_board_record(
        client,
        config,
        store,
        board,
        ticket_ref,
        channel_id=channel_id,
        record_id_hint=record_id_hint,
    )
    list_id = board.list_id

    grant_list_access(
        client,
        list_id,
        channel_id=channel_id or (board.channel_ids[0] if board.channel_ids else ""),
    )
    schema = load_schema(client, list_id, store)
    cells_list: list[dict[str, Any]] = []

    if status.strip():
        col = column_by_name(schema, board.columns.status or "Status")
        field = field_payload(col, status.strip()) if col else None
        if field:
            cells_list.append({"row_id": record_id, **field})

    if assignee_user_id.strip():
        col = column_by_name(schema, board.columns.assignee or "Assignee")
        field = (
            field_payload(col, "", user_ids=[assignee_user_id.strip()]) if col else None
        )
        if field:
            cells_list.append({"row_id": record_id, **field})

    if severity.strip():
        col = resolve_severity_column(schema, board.columns)
        normalized = normalize_board_severity(severity)
        field = field_payload(col, normalized) if col and normalized else None
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
