"""SQLite storage for Slack channel workflows and List board bindings."""

from __future__ import annotations

import json
import logging
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Literal

from backend.paths import db_path

logger = logging.getLogger(__name__)

TicketSystem = Literal["ask", "slack_list", "jira"]

_DEFAULT_COLUMNS: dict[str, str] = {
    "title": "Name",
    "status": "Status",
    "severity": "Severity",
    "assignee": "Assignee",
    "merchant": "Merchant Name",
    "merchant_domain": "Merchant Domain",
    "details": "Ticket Details",
    "display_id": "",
}


def init_slack_workflows_db(db_file: Path) -> None:
    conn = sqlite3.connect(db_file, timeout=10.0)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS slack_channel_workflows (
            channel_id TEXT PRIMARY KEY,
            channel_name TEXT NOT NULL DEFAULT '',
            ticket_system TEXT NOT NULL DEFAULT 'ask',
            jira_project_key TEXT NOT NULL DEFAULT '',
            enabled INTEGER NOT NULL DEFAULT 1,
            updated_at REAL NOT NULL
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS slack_board_bindings (
            id TEXT PRIMARY KEY,
            board_key TEXT NOT NULL,
            list_id TEXT NOT NULL,
            list_name TEXT NOT NULL DEFAULT '',
            channel_id TEXT NOT NULL UNIQUE,
            channel_name TEXT NOT NULL DEFAULT '',
            display_id_prefix TEXT NOT NULL DEFAULT 'TS',
            next_display_num INTEGER NOT NULL DEFAULT 1,
            default_status TEXT NOT NULL DEFAULT 'Not picked',
            auto_approve_writes INTEGER NOT NULL DEFAULT 0,
            column_map_json TEXT NOT NULL DEFAULT '{}',
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        )
        """
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_slack_board_bindings_board_key ON slack_board_bindings(board_key)"
    )
    conn.commit()
    conn.close()


def _connect(data_dir: Path | None) -> sqlite3.Connection:
    db_file = db_path(data_dir)
    init_slack_workflows_db(db_file)
    conn = sqlite3.connect(db_file, timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn


def _row_to_channel_workflow(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "channel_id": row["channel_id"],
        "channel_name": row["channel_name"] or "",
        "ticket_system": row["ticket_system"] or "ask",
        "jira_project_key": row["jira_project_key"] or "",
        "enabled": bool(row["enabled"]),
        "updated_at": row["updated_at"],
    }


def _parse_columns(raw: str) -> dict[str, str]:
    try:
        parsed = json.loads(raw or "{}")
    except json.JSONDecodeError:
        parsed = {}
    out = dict(_DEFAULT_COLUMNS)
    if isinstance(parsed, dict):
        for key, value in parsed.items():
            if key in out and value is not None:
                out[key] = str(value)
    return out


def _row_to_board_binding(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "board_key": row["board_key"],
        "list_id": row["list_id"],
        "list_name": row["list_name"] or "",
        "channel_id": row["channel_id"],
        "channel_name": row["channel_name"] or "",
        "display_id_prefix": row["display_id_prefix"] or "TS",
        "next_display_num": int(row["next_display_num"] or 1),
        "default_status": row["default_status"] or "Not picked",
        "auto_approve_writes": bool(row["auto_approve_writes"]),
        "columns": _parse_columns(row["column_map_json"] or "{}"),
        "enabled": bool(row["enabled"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def db_has_active_bindings(data_dir: Path | None) -> bool:
    conn = _connect(data_dir)
    try:
        row = conn.execute(
            "SELECT 1 FROM slack_board_bindings WHERE enabled = 1 LIMIT 1"
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def db_list_channel_workflows(data_dir: Path | None) -> list[dict[str, Any]]:
    conn = _connect(data_dir)
    try:
        rows = conn.execute(
            "SELECT * FROM slack_channel_workflows ORDER BY channel_name, channel_id"
        ).fetchall()
        return [_row_to_channel_workflow(row) for row in rows]
    finally:
        conn.close()


def db_get_channel_workflow(data_dir: Path | None, channel_id: str) -> dict[str, Any] | None:
    conn = _connect(data_dir)
    try:
        row = conn.execute(
            "SELECT * FROM slack_channel_workflows WHERE channel_id = ?",
            (channel_id.strip(),),
        ).fetchone()
        return _row_to_channel_workflow(row) if row else None
    finally:
        conn.close()


def db_upsert_channel_workflow(
    data_dir: Path | None,
    *,
    channel_id: str,
    channel_name: str = "",
    ticket_system: TicketSystem = "ask",
    jira_project_key: str = "",
    enabled: bool = True,
) -> dict[str, Any]:
    conn = _connect(data_dir)
    now = time.time()
    cid = channel_id.strip()
    try:
        conn.execute(
            """
            INSERT INTO slack_channel_workflows (
                channel_id, channel_name, ticket_system, jira_project_key, enabled, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(channel_id) DO UPDATE SET
                channel_name = excluded.channel_name,
                ticket_system = excluded.ticket_system,
                jira_project_key = excluded.jira_project_key,
                enabled = excluded.enabled,
                updated_at = excluded.updated_at
            """,
            (
                cid,
                channel_name.strip(),
                ticket_system,
                jira_project_key.strip().upper(),
                1 if enabled else 0,
                now,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    result = db_get_channel_workflow(data_dir, cid)
    assert result is not None
    return result


def db_delete_channel_workflow(data_dir: Path | None, channel_id: str) -> bool:
    conn = _connect(data_dir)
    try:
        cur = conn.execute(
            "DELETE FROM slack_channel_workflows WHERE channel_id = ?",
            (channel_id.strip(),),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def db_list_board_bindings(data_dir: Path | None) -> list[dict[str, Any]]:
    conn = _connect(data_dir)
    try:
        rows = conn.execute(
            "SELECT * FROM slack_board_bindings ORDER BY channel_name, board_key"
        ).fetchall()
        return [_row_to_board_binding(row) for row in rows]
    finally:
        conn.close()


def db_get_board_binding(data_dir: Path | None, binding_id: str) -> dict[str, Any] | None:
    conn = _connect(data_dir)
    try:
        row = conn.execute(
            "SELECT * FROM slack_board_bindings WHERE id = ?",
            (binding_id.strip(),),
        ).fetchone()
        return _row_to_board_binding(row) if row else None
    finally:
        conn.close()


def db_get_board_binding_for_channel(
    data_dir: Path | None,
    channel_id: str,
) -> dict[str, Any] | None:
    conn = _connect(data_dir)
    try:
        row = conn.execute(
            """
            SELECT * FROM slack_board_bindings
            WHERE channel_id = ? AND enabled = 1
            LIMIT 1
            """,
            (channel_id.strip(),),
        ).fetchone()
        return _row_to_board_binding(row) if row else None
    finally:
        conn.close()


def db_create_board_binding(
    data_dir: Path | None,
    *,
    board_key: str,
    list_id: str,
    channel_id: str,
    channel_name: str = "",
    list_name: str = "",
    display_id_prefix: str = "TS",
    next_display_num: int = 1,
    default_status: str = "Not picked",
    auto_approve_writes: bool = False,
    columns: dict[str, str] | None = None,
    enabled: bool = True,
) -> dict[str, Any]:
    conn = _connect(data_dir)
    binding_id = uuid.uuid4().hex
    now = time.time()
    col_map = dict(_DEFAULT_COLUMNS)
    if columns:
        col_map.update({k: str(v) for k, v in columns.items() if k in col_map})
    try:
        conn.execute(
            """
            INSERT INTO slack_board_bindings (
                id, board_key, list_id, list_name, channel_id, channel_name,
                display_id_prefix, next_display_num, default_status,
                auto_approve_writes, column_map_json, enabled, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                binding_id,
                board_key.strip(),
                list_id.strip(),
                list_name.strip(),
                channel_id.strip(),
                channel_name.strip(),
                (display_id_prefix or "TS").strip(),
                max(1, int(next_display_num)),
                (default_status or "Not picked").strip(),
                1 if auto_approve_writes else 0,
                json.dumps(col_map),
                1 if enabled else 0,
                now,
                now,
            ),
        )
        conn.commit()
    except sqlite3.IntegrityError as exc:
        raise ValueError("A board binding already exists for this channel.") from exc
    finally:
        conn.close()
    result = db_get_board_binding(data_dir, binding_id)
    assert result is not None
    return result


def db_update_board_binding(
    data_dir: Path | None,
    binding_id: str,
    *,
    board_key: str | None = None,
    list_id: str | None = None,
    list_name: str | None = None,
    channel_name: str | None = None,
    display_id_prefix: str | None = None,
    next_display_num: int | None = None,
    default_status: str | None = None,
    auto_approve_writes: bool | None = None,
    columns: dict[str, str] | None = None,
    enabled: bool | None = None,
) -> dict[str, Any] | None:
    existing = db_get_board_binding(data_dir, binding_id)
    if not existing:
        return None
    conn = _connect(data_dir)
    now = time.time()
    fields: dict[str, Any] = {
        "board_key": board_key if board_key is not None else existing["board_key"],
        "list_id": list_id if list_id is not None else existing["list_id"],
        "list_name": list_name if list_name is not None else existing["list_name"],
        "channel_name": channel_name if channel_name is not None else existing["channel_name"],
        "display_id_prefix": display_id_prefix
        if display_id_prefix is not None
        else existing["display_id_prefix"],
        "next_display_num": next_display_num
        if next_display_num is not None
        else existing["next_display_num"],
        "default_status": default_status
        if default_status is not None
        else existing["default_status"],
        "auto_approve_writes": auto_approve_writes
        if auto_approve_writes is not None
        else existing["auto_approve_writes"],
        "enabled": enabled if enabled is not None else existing["enabled"],
        "updated_at": now,
    }
    col_map = dict(existing.get("columns") or _DEFAULT_COLUMNS)
    if columns:
        col_map.update({k: str(v) for k, v in columns.items() if k in _DEFAULT_COLUMNS})
    fields["column_map_json"] = json.dumps(col_map)
    try:
        conn.execute(
            """
            UPDATE slack_board_bindings SET
                board_key = ?, list_id = ?, list_name = ?, channel_name = ?,
                display_id_prefix = ?, next_display_num = ?, default_status = ?,
                auto_approve_writes = ?, column_map_json = ?, enabled = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                fields["board_key"],
                fields["list_id"],
                fields["list_name"],
                fields["channel_name"],
                fields["display_id_prefix"],
                max(1, int(fields["next_display_num"])),
                fields["default_status"],
                1 if fields["auto_approve_writes"] else 0,
                fields["column_map_json"],
                1 if fields["enabled"] else 0,
                now,
                binding_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return db_get_board_binding(data_dir, binding_id)


def db_delete_board_binding(data_dir: Path | None, binding_id: str) -> bool:
    conn = _connect(data_dir)
    try:
        cur = conn.execute("DELETE FROM slack_board_bindings WHERE id = ?", (binding_id.strip(),))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def db_bump_display_id(
    data_dir: Path | None,
    *,
    channel_id: str,
    prefix: str | None = None,
) -> str | None:
    """Allocate the next display id for a channel binding (one counter per channel)."""
    conn = _connect(data_dir)
    cid = channel_id.strip()
    try:
        row = conn.execute(
            """
            SELECT id, display_id_prefix, next_display_num
            FROM slack_board_bindings
            WHERE channel_id = ? AND enabled = 1
            LIMIT 1
            """,
            (cid,),
        ).fetchone()
        if not row:
            return None
        use_prefix = (prefix or row["display_id_prefix"] or "TS").strip()
        num = int(row["next_display_num"] or 1)
        display_id = f"{use_prefix}-{num}"
        conn.execute(
            """
            UPDATE slack_board_bindings
            SET next_display_num = ?, display_id_prefix = ?, updated_at = ?
            WHERE id = ?
            """,
            (num + 1, use_prefix, time.time(), row["id"]),
        )
        conn.commit()
        return display_id
    finally:
        conn.close()
