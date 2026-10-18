"""Slack List column/field payload helpers (HTTP shape, not CRUD)."""

from __future__ import annotations

from typing import Any

from backend.db.slack_board_store import SlackBoardStore
from backend.integrations.slack.lists_client import list_columns


def column_by_name(schema: list[dict[str, Any]], label: str) -> dict[str, Any] | None:
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


def resolve_severity_column(
    schema: list[dict[str, Any]],
    cols: Any,
) -> dict[str, Any] | None:
    for label in (
        getattr(cols, "severity", None) or "Severity",
        "Priority",
        "Severity",
    ):
        col = column_by_name(schema, str(label))
        if col:
            return col
    return None


def primary_column(schema: list[dict[str, Any]]) -> dict[str, Any] | None:
    for col in schema:
        if isinstance(col, dict) and col.get("is_primary_column"):
            return col
    return None


def resolve_title_column(
    schema: list[dict[str, Any]],
    configured_label: str,
) -> dict[str, Any] | None:
    for label in (configured_label, "Name", "Title", "name", "title"):
        if not label:
            continue
        col = column_by_name(schema, label)
        if col:
            return col
    return primary_column(schema)


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


def select_value_for_label(column: dict[str, Any], label: str) -> str | None:
    choices = ((column.get("options") or {}).get("choices") or [])
    target = (label or "").strip().lower()
    for choice in choices:
        if not isinstance(choice, dict):
            continue
        if str(choice.get("label") or "").strip().lower() == target:
            return str(choice.get("value") or "")
    return None


def rich_text_blocks(value: str) -> list[dict[str, Any]]:
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


def field_payload(
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
        selected = select_value_for_label(column, value)
        if not selected:
            return None
        payload["select"] = [selected]
        return payload
    if not (value or "").strip():
        return None
    payload["rich_text"] = rich_text_blocks(value.strip())
    return payload


def append_field(
    initial_fields: list[dict[str, Any]],
    column: dict[str, Any] | None,
    value: str,
    *,
    user_ids: list[str] | None = None,
) -> None:
    if not column:
        return
    field = field_payload(column, value, user_ids=user_ids)
    if field:
        initial_fields.append(field)


def resolve_display_id_column(
    schema: list[dict[str, Any]],
    cols: Any,
) -> dict[str, Any] | None:
    for label in (
        getattr(cols, "display_id", None) or "",
        "Display ID",
        "display_id",
    ):
        if not (label or "").strip():
            continue
        col = column_by_name(schema, str(label))
        if col:
            return col
    for col in schema:
        if not isinstance(col, dict):
            continue
        name = str(col.get("name") or "").lower()
        key = str(col.get("key") or "").lower()
        if "display" in name and "id" in name:
            return col
        if key == "display_id":
            return col
    return None


# Compat aliases for tests that imported underscored names from board_service.
_column_by_name = column_by_name
_resolve_title_column = resolve_title_column
_field_payload = field_payload
