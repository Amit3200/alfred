"""SQLite storage and query utilities for scheduled cron jobs."""

from __future__ import annotations

import logging
import sqlite3
import time
from pathlib import Path
from typing import Any

from backend.paths import db_path

logger = logging.getLogger(__name__)


def init_schedule_db(db_file: Path) -> None:
    """Ensure the scheduled_jobs table exists in the database."""
    conn = sqlite3.connect(db_file, timeout=10.0)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS scheduled_jobs (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            cron_expression TEXT NOT NULL,
            skill_name TEXT NOT NULL,
            channel_id TEXT,
            user_id TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            last_run_at REAL,
            last_run_status TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def db_create_schedule(
    data_dir: Path | None,
    job_id: str,
    name: str,
    description: str | None,
    cron_expression: str,
    skill_name: str,
    channel_id: str | None,
    user_id: str | None,
) -> None:
    """Insert a new scheduled job or replace an existing one."""
    db_file = db_path(data_dir)
    init_schedule_db(db_file)
    now = time.time()
    conn = sqlite3.connect(db_file, timeout=10.0)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT OR REPLACE INTO scheduled_jobs (
            id, name, description, cron_expression, skill_name,
            channel_id, user_id, status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            job_id,
            name,
            description,
            cron_expression,
            skill_name,
            channel_id,
            user_id,
            "active",
            now,
            now,
        ),
    )
    conn.commit()
    conn.close()


def db_list_schedules(data_dir: Path | None) -> list[dict[str, Any]]:
    """List all configured scheduled jobs."""
    db_file = db_path(data_dir)
    init_schedule_db(db_file)
    conn = sqlite3.connect(db_file, timeout=10.0)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM scheduled_jobs ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def db_delete_schedule(data_dir: Path | None, job_id: str) -> bool:
    """Delete a scheduled job by its unique ID."""
    db_file = db_path(data_dir)
    init_schedule_db(db_file)
    conn = sqlite3.connect(db_file, timeout=10.0)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM scheduled_jobs WHERE id = ?", (job_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def db_toggle_schedule(data_dir: Path | None, job_id: str, active: bool) -> bool:
    """Toggle a scheduled job status between active and inactive."""
    db_file = db_path(data_dir)
    init_schedule_db(db_file)
    status = "active" if active else "inactive"
    now = time.time()
    conn = sqlite3.connect(db_file, timeout=10.0)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE scheduled_jobs SET status = ?, updated_at = ? WHERE id = ?",
        (status, now, job_id),
    )
    updated = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return updated


def db_update_last_run(
    data_dir: Path | None,
    job_id: str,
    status: str,
) -> None:
    """Update execution timestamp and status for a scheduled job."""
    db_file = db_path(data_dir)
    init_schedule_db(db_file)
    now = time.time()
    conn = sqlite3.connect(db_file, timeout=10.0)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE scheduled_jobs SET last_run_at = ?, last_run_status = ? WHERE id = ?",
        (now, status, job_id),
    )
    conn.commit()
    conn.close()
