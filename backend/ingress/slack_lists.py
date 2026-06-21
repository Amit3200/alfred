"""Resolve Slack List record links in channel messages into structured ticket context."""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import parse_qs, urlparse

from backend.ingress.slack_messages import rich_text_to_plain

logger = logging.getLogger(__name__)

_LIST_URL_RE = re.compile(
    r"https?://[^\s>|]+/lists/[^/\s>|]+/([A-Z0-9]+)(?:\?[^\s>|]*)?",
    re.IGNORECASE,
)
_RECORD_ID_RE = re.compile(r"record_id=([A-Za-z0-9]+)")

_TICKET_INTENT_MARKERS = (
    "ticket",
    "tickets",
    "severity",
    "serverity",  # common typo
    "open item",
    "bug",
    "reported",
    "tech-support",
    "category",
    "issues reported",
    "classify",
)

MAX_LIST_RECORDS = 30


def wants_slack_list_enrichment(intent: str) -> bool:
    lower = intent.lower()
    return any(marker in lower for marker in _TICKET_INTENT_MARKERS)


def extract_list_refs(messages: list[dict]) -> list[tuple[str, str]]:
    """Return unique (list_id, record_id) pairs referenced in channel messages."""
    seen: set[tuple[str, str]] = set()
    refs: list[tuple[str, str]] = []
    for message in messages:
        for blob in _message_text_blobs(message):
            for list_id, record_id in _refs_from_text(blob):
                key = (list_id, record_id)
                if key not in seen:
                    seen.add(key)
                    refs.append(key)
    return refs[:MAX_LIST_RECORDS]


def enrich_channel_context_with_lists(
    client: Any,
    messages: list[dict],
    *,
    intent: str,
) -> str | None:
    """Load Slack List ticket fields linked from channel/thread messages."""
    if not wants_slack_list_enrichment(intent):
        return None

    rows: list[str] = []
    seen_records: set[str] = set()

    for record_id, record, schema in extract_embedded_list_records(messages):
        if record_id in seen_records:
            continue
        seen_records.add(record_id)
        formatted = format_list_record(record, schema=schema)
        if formatted:
            rows.append(formatted)

    refs = extract_list_refs(messages)
    for list_id, record_id in refs:
        if record_id in seen_records:
            continue
        record = _fetch_list_record(client, list_id, record_id)
        if not record:
            continue
        seen_records.add(record_id)
        formatted = format_list_record(record)
        if formatted:
            rows.append(formatted)

    if not rows:
        if refs:
            return (
                "Slack List tickets: ticket links were found in channel messages, "
                "but list record details could not be loaded. "
                "Confirm the bot has `lists:read`, reinstall the app, and restart Alfred."
            )
        return None

    return "Slack List tickets (from linked records, oldest → newest in message order):\n" + "\n\n".join(
        rows
    )


def extract_embedded_list_records(
    messages: list[dict],
) -> list[tuple[str, dict[str, Any], list[dict[str, Any]]]]:
    """Parse list_record payloads Slack embeds in workflow cards and link unfurls."""
    results: list[tuple[str, dict[str, Any], list[dict[str, Any]]]] = []
    seen: set[str] = set()
    for message in messages:
        for attachment in message.get("attachments") or []:
            if not isinstance(attachment, dict):
                continue
            list_record = attachment.get("list_record")
            if not isinstance(list_record, dict):
                continue
            record = list_record.get("record")
            if not isinstance(record, dict):
                continue
            record_id = str(record.get("record_id") or record.get("id") or attachment.get("list_record_id") or "")
            if not record_id or record_id in seen:
                continue
            seen.add(record_id)
            schema = list_record.get("schema") or []
            results.append((record_id, record, schema if isinstance(schema, list) else []))
    return results


def format_list_record(
    record: dict[str, Any],
    *,
    schema: list[dict[str, Any]] | None = None,
) -> str:
    record_id = record.get("record_id") or record.get("id") or "unknown"
    lines = [f"Ticket `{record_id}`:"]
    fields = record.get("fields") or []
    if not isinstance(fields, list):
        return ""

    schema_by_key = _schema_by_key(schema or [])
    schema_by_column = _schema_by_column(schema or [])

    for field in fields:
        if not isinstance(field, dict):
            continue
        label = _field_label(field, schema_by_key=schema_by_key, schema_by_column=schema_by_column)
        value = _field_value(field, schema_by_key=schema_by_key, schema_by_column=schema_by_column)
        if label and value:
            lines.append(f"  {label}: {value}")

    if len(lines) == 1:
        title = _field_value_by_key(fields, "title", schema=schema) or _field_value_by_key(
            fields, "name", schema=schema
        )
        if title:
            lines.append(f"  title: {title}")
        else:
            return ""
    return "\n".join(lines)


def _fetch_list_record(client: Any, list_id: str, record_id: str) -> dict[str, Any] | None:
    try:
        response = client.api_call(
            "slackLists.items.info",
            json={"list_id": list_id, "id": record_id},
        )
    except Exception as exc:
        logger.warning("slackLists.items.info failed for %s/%s: %s", list_id, record_id, exc)
        return None
    if not response.get("ok"):
        logger.warning(
            "slackLists.items.info error for %s/%s: %s",
            list_id,
            record_id,
            response.get("error"),
        )
        return None
    record = response.get("record")
    return record if isinstance(record, dict) else None


def _message_text_blobs(message: dict) -> list[str]:
    blobs: list[str] = []
    text = message.get("text")
    if isinstance(text, str) and text.strip():
        blobs.append(text)
    for attachment in message.get("attachments") or []:
        if not isinstance(attachment, dict):
            continue
        for key in ("text", "pretext", "title", "fallback"):
            value = attachment.get(key)
            if isinstance(value, str) and value.strip():
                blobs.append(value)
        for field in attachment.get("fields") or []:
            if not isinstance(field, dict):
                continue
            title = field.get("title") or ""
            value = field.get("value") or ""
            if title or value:
                blobs.append(f"{title}: {value}")
    for block in message.get("blocks") or []:
        blobs.extend(_block_text_blobs(block))
    return blobs


def _block_text_blobs(block: dict) -> list[str]:
    if not isinstance(block, dict):
        return []
    block_type = block.get("type")
    chunks: list[str] = []
    if block_type in ("section", "header"):
        text_obj = block.get("text") or {}
        if isinstance(text_obj, dict) and text_obj.get("text"):
            chunks.append(str(text_obj["text"]))
    elif block_type == "rich_text":
        chunks.append(rich_text_to_plain(block))
    elif block_type == "context":
        for element in block.get("elements") or []:
            if isinstance(element, dict) and element.get("text"):
                chunks.append(str(element["text"]))
    return [c for c in chunks if c.strip()]


def _refs_from_text(text: str) -> list[tuple[str, str]]:
    refs: list[tuple[str, str]] = []
    for match in _LIST_URL_RE.finditer(text):
        list_id = match.group(1)
        query = urlparse(match.group(0)).query
        record_id = parse_qs(query).get("record_id", [None])[0]
        if not record_id:
            record_match = _RECORD_ID_RE.search(text[match.start() : match.start() + 120])
            record_id = record_match.group(1) if record_match else None
        if list_id and record_id:
            refs.append((list_id, record_id))
    return refs


def _field_label(
    field: dict[str, Any],
    *,
    schema_by_key: dict[str, dict[str, Any]] | None = None,
    schema_by_column: dict[str, dict[str, Any]] | None = None,
) -> str:
    column_id = field.get("column_id")
    if column_id and schema_by_column and str(column_id) in schema_by_column:
        name = schema_by_column[str(column_id)].get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    for key in ("key", "name", "column_key"):
        value = field.get(key)
        if isinstance(value, str) and value.strip():
            key_text = value.strip()
            if schema_by_key and key_text in schema_by_key:
                name = schema_by_key[key_text].get("name")
                if isinstance(name, str) and name.strip():
                    return name.strip()
            if key_text.startswith("Col"):
                return "Field"
            return key_text.replace("_", " ").title()
    return str(column_id) if column_id else "Field"


def _field_value(
    field: dict[str, Any],
    *,
    schema_by_key: dict[str, dict[str, Any]] | None = None,
    schema_by_column: dict[str, dict[str, Any]] | None = None,
) -> str:
    schema_col = _schema_column_for_field(field, schema_by_key, schema_by_column)
    if schema_col and schema_col.get("type") == "select":
        select_label = _resolve_select_value(field, schema_col)
        if select_label:
            return select_label

    text_fallback = field.get("text")
    if isinstance(text_fallback, str) and text_fallback.strip():
        return text_fallback.strip()
    rich = field.get("rich_text")
    if isinstance(rich, list):
        parsed = _value_from_rich_payload(rich)
        if parsed:
            return parsed
    for key in ("value", "name"):
        raw = field.get(key)
        if raw is None:
            continue
        if isinstance(raw, (int, float)) and schema_col and schema_col.get("type") in (
            "created_time",
            "date",
            "due_date",
        ):
            return _format_timestamp(raw)
        if isinstance(raw, list):
            if raw and isinstance(raw[0], dict):
                rich = _value_from_rich_payload(raw)
                if rich:
                    return rich
            parts = [str(item).strip() for item in raw if str(item).strip()]
            if parts:
                return ", ".join(parts)
        if isinstance(raw, dict):
            rich = _value_from_rich_payload([raw])
            if rich:
                return rich
        text = str(raw).strip()
        if text and text not in ("[]", "{}"):
            return text
    select = field.get("select") or field.get("selected_options")
    if isinstance(select, list) and select:
        if schema_col:
            return _resolve_select_value(field, schema_col)
        return ", ".join(str(item) for item in select if str(item).strip())
    return ""


def _schema_by_key(schema: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    mapping: dict[str, dict[str, Any]] = {}
    for column in schema:
        if not isinstance(column, dict):
            continue
        key = column.get("key")
        if isinstance(key, str) and key:
            mapping[key] = column
    return mapping


def _schema_by_column(schema: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    mapping: dict[str, dict[str, Any]] = {}
    for column in schema:
        if not isinstance(column, dict):
            continue
        column_id = column.get("id")
        if column_id is not None:
            mapping[str(column_id)] = column
    return mapping


def _schema_column_for_field(
    field: dict[str, Any],
    schema_by_key: dict[str, dict[str, Any]] | None,
    schema_by_column: dict[str, dict[str, Any]] | None,
) -> dict[str, Any] | None:
    column_id = field.get("column_id")
    if column_id is not None and schema_by_column and str(column_id) in schema_by_column:
        return schema_by_column[str(column_id)]
    key = field.get("key")
    if isinstance(key, str) and schema_by_key and key in schema_by_key:
        return schema_by_key[key]
    return None


def _resolve_select_value(field: dict[str, Any], schema_col: dict[str, Any]) -> str:
    choices = ((schema_col.get("options") or {}).get("choices") or [])
    value_to_label = {
        str(choice.get("value")): str(choice.get("label") or choice.get("value"))
        for choice in choices
        if isinstance(choice, dict) and choice.get("value") is not None
    }
    selected = field.get("select")
    if not isinstance(selected, list) or not selected:
        raw = field.get("value")
        selected = [raw] if isinstance(raw, str) and raw else []
    labels = [value_to_label.get(str(item), str(item)) for item in selected if str(item).strip()]
    return ", ".join(labels)


def _format_timestamp(raw: int | float) -> str:
    from datetime import datetime, timezone

    try:
        return datetime.fromtimestamp(float(raw), tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except (ValueError, OSError, TypeError):
        return str(raw)


def _value_from_rich_payload(payload: list[Any]) -> str:
    parts: list[str] = []
    for item in payload:
        if isinstance(item, dict) and item.get("type") == "rich_text":
            text = rich_text_to_plain(item)
            if text:
                parts.append(text)
    return "\n".join(parts)


def _field_value_by_key(
    fields: list[Any],
    key: str,
    *,
    schema: list[dict[str, Any]] | None = None,
) -> str:
    schema_by_key = _schema_by_key(schema or [])
    schema_by_column = _schema_by_column(schema or [])
    for field in fields:
        if isinstance(field, dict) and str(field.get("key") or "").lower() == key.lower():
            return _field_value(field, schema_by_key=schema_by_key, schema_by_column=schema_by_column)
    return ""
