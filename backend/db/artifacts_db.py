"""SQLite index for content-addressed HTML presentation artifacts."""

from __future__ import annotations

import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from backend.paths import db_path

MAX_SLUG_LEN = 64


class SlugOwnershipError(PermissionError):
    """Raised when a user tries to manage a slug owned by someone else."""


def init_artifacts_db(db_file: Path) -> None:
    conn = sqlite3.connect(db_file, timeout=10.0)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS artifact_uploads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid TEXT NOT NULL UNIQUE,
            sha256 TEXT NOT NULL,
            slug TEXT NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            uploaded_by TEXT NOT NULL DEFAULT 'admin',
            uploaded_at REAL NOT NULL,
            size_bytes INTEGER NOT NULL,
            is_latest INTEGER NOT NULL DEFAULT 0,
            UNIQUE(slug, sha256)
        )
        """
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_artifact_slug ON artifact_uploads(slug)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_artifact_sha ON artifact_uploads(sha256)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_artifact_uploader ON artifact_uploads(uploaded_by)"
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_artifact_slug_latest
        ON artifact_uploads(slug, is_latest)
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS artifact_slugs (
            slug TEXT PRIMARY KEY,
            owner_key TEXT NOT NULL,
            owner_label TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        )
        """
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_artifact_slug_owner ON artifact_slugs(owner_key)"
    )
    conn.commit()
    conn.close()
    _migrate_artifacts_db(db_file)


def _migrate_artifacts_db(db_file: Path) -> None:
    conn = sqlite3.connect(db_file, timeout=10.0)
    cursor = conn.cursor()
    columns = {row[1] for row in cursor.execute("PRAGMA table_info(artifact_uploads)")}
    if "source" not in columns:
        cursor.execute(
            "ALTER TABLE artifact_uploads ADD COLUMN source TEXT NOT NULL DEFAULT 'api'"
        )
    if "slack_user_id" not in columns:
        cursor.execute(
            "ALTER TABLE artifact_uploads ADD COLUMN slack_user_id TEXT NOT NULL DEFAULT ''"
        )
    conn.commit()
    conn.close()


def _connect(db_file: Path) -> sqlite3.Connection:
    init_artifacts_db(db_file)
    conn = sqlite3.connect(db_file, timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn


def normalize_slug(raw: str) -> str:
    slug = raw.strip().lower()
    slug = slug.replace("_", "-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    slug = slug.strip("-")
    if not slug:
        raise ValueError("Slug is required")
    if len(slug) > MAX_SLUG_LEN:
        raise ValueError(f"Slug must be at most {MAX_SLUG_LEN} characters")
    allowed = set("abcdefghijklmnopqrstuvwxyz0123456789-")
    if not all(ch in allowed for ch in slug):
        raise ValueError("Slug may only contain lowercase letters, digits, and hyphens")
    if slug[0] == "-" or slug[-1] == "-":
        raise ValueError("Slug may not start or end with a hyphen")
    return slug


def get_slug_owner(db_file: Path, slug: str) -> dict[str, Any] | None:
    slug = normalize_slug(slug)
    conn = _connect(db_file)
    try:
        row = conn.execute(
            """
            SELECT slug, owner_key, owner_label, created_at, updated_at
            FROM artifact_slugs
            WHERE slug = ?
            """,
            (slug,),
        ).fetchone()
        if not row:
            return None
        return {
            "slug": row["slug"],
            "owner_key": row["owner_key"],
            "owner_label": row["owner_label"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
    finally:
        conn.close()


def assert_slug_owner(db_file: Path, slug: str, owner_key: str) -> None:
    owner = get_slug_owner(db_file, slug)
    if owner is None:
        return
    if owner["owner_key"] != owner_key.strip():
        raise SlugOwnershipError(f"Slug '{slug}' is owned by another user")


def claim_or_update_slug_owner(
    db_file: Path,
    *,
    slug: str,
    owner_key: str,
    owner_label: str,
) -> None:
    slug = normalize_slug(slug)
    key = owner_key.strip()
    label = owner_label.strip() or key
    now = time.time()
    conn = _connect(db_file)
    try:
        row = conn.execute(
            "SELECT owner_key FROM artifact_slugs WHERE slug = ?",
            (slug,),
        ).fetchone()
        if row is None:
            conn.execute(
                """
                INSERT INTO artifact_slugs (slug, owner_key, owner_label, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (slug, key, label, now, now),
            )
        elif row["owner_key"] != key:
            raise SlugOwnershipError(f"Slug '{slug}' is owned by another user")
        else:
            conn.execute(
                """
                UPDATE artifact_slugs
                SET owner_label = ?, updated_at = ?
                WHERE slug = ?
                """,
                (label, now, slug),
            )
        conn.commit()
    finally:
        conn.close()


def record_upload(
    db_file: Path,
    *,
    sha256: str,
    slug: str,
    title: str,
    uploaded_by: str,
    owner_key: str,
    size_bytes: int,
    source: str = "api",
    slack_user_id: str = "",
) -> dict[str, Any]:
    """Insert a new version and mark it as latest for the slug."""
    slug = normalize_slug(slug)
    digest = sha256.lower().strip()
    if len(digest) != 64:
        raise ValueError("Invalid sha256 digest")
    claim_or_update_slug_owner(
        db_file,
        slug=slug,
        owner_key=owner_key,
        owner_label=uploaded_by,
    )
    row_uuid = str(uuid.uuid4())
    now = time.time()

    conn = _connect(db_file)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE artifact_uploads SET is_latest = 0 WHERE slug = ?",
            (slug,),
        )
        cursor.execute(
            """
            INSERT INTO artifact_uploads (
                uuid, sha256, slug, title, uploaded_by, uploaded_at, size_bytes, is_latest,
                source, slack_user_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            ON CONFLICT(slug, sha256) DO UPDATE SET
                title = excluded.title,
                uploaded_by = excluded.uploaded_by,
                uploaded_at = excluded.uploaded_at,
                size_bytes = excluded.size_bytes,
                is_latest = 1,
                source = excluded.source,
                slack_user_id = excluded.slack_user_id
            """,
            (
                row_uuid,
                digest,
                slug,
                title.strip(),
                uploaded_by.strip() or "admin",
                now,
                size_bytes,
                source.strip() or "api",
                slack_user_id.strip(),
            ),
        )
        conn.commit()
    finally:
        conn.close()

    return get_latest_by_slug(db_file, slug) or {}


def record_sha_upload(
    db_file: Path,
    *,
    sha256: str,
    title: str,
    uploaded_by: str,
    owner_key: str,
    size_bytes: int,
    source: str = "api",
    slack_user_id: str = "",
) -> dict[str, Any]:
    """Index a content-addressed upload without claiming a user slug."""
    _ = owner_key  # reserved for future per-actor sha listings
    digest = sha256.lower().strip()
    if len(digest) != 64:
        raise ValueError("Invalid sha256 digest")
    row_uuid = str(uuid.uuid4())
    now = time.time()
    conn = _connect(db_file)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO artifact_uploads (
                uuid, sha256, slug, title, uploaded_by, uploaded_at, size_bytes, is_latest,
                source, slack_user_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            ON CONFLICT(slug, sha256) DO UPDATE SET
                title = excluded.title,
                uploaded_by = excluded.uploaded_by,
                uploaded_at = excluded.uploaded_at,
                size_bytes = excluded.size_bytes,
                source = excluded.source,
                slack_user_id = excluded.slack_user_id
            """,
            (
                row_uuid,
                digest,
                digest,
                title.strip(),
                uploaded_by.strip() or "admin",
                now,
                size_bytes,
                source.strip() or "api",
                slack_user_id.strip(),
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return get_by_sha(db_file, digest) or {}


def get_latest_by_slug(db_file: Path, slug: str) -> dict[str, Any] | None:
    slug = normalize_slug(slug)
    conn = _connect(db_file)
    try:
        row = conn.execute(
            """
            SELECT uuid, sha256, slug, title, uploaded_by, uploaded_at, size_bytes, is_latest
            FROM artifact_uploads
            WHERE slug = ? AND is_latest = 1
            ORDER BY uploaded_at DESC
            LIMIT 1
            """,
            (slug,),
        ).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


def get_by_sha(db_file: Path, sha256: str) -> dict[str, Any] | None:
    digest = sha256.lower().strip()
    conn = _connect(db_file)
    try:
        row = conn.execute(
            """
            SELECT uuid, sha256, slug, title, uploaded_by, uploaded_at, size_bytes, is_latest
            FROM artifact_uploads
            WHERE sha256 = ?
            ORDER BY uploaded_at DESC
            LIMIT 1
            """,
            (digest,),
        ).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


def list_versions(db_file: Path, slug: str) -> list[dict[str, Any]]:
    slug = normalize_slug(slug)
    conn = _connect(db_file)
    try:
        rows = conn.execute(
            """
            SELECT uuid, sha256, slug, title, uploaded_by, uploaded_at, size_bytes, is_latest
            FROM artifact_uploads
            WHERE slug = ?
            ORDER BY uploaded_at DESC
            """,
            (slug,),
        ).fetchall()
        return [_row_to_dict(row) for row in rows]
    finally:
        conn.close()


def list_mine(db_file: Path, *, owner_key: str, limit: int = 100) -> list[dict[str, Any]]:
    """Latest upload per owned slug for the given actor key."""
    conn = _connect(db_file)
    try:
        rows = conn.execute(
            """
            SELECT a.uuid, a.sha256, a.slug, a.title, a.uploaded_by,
                   a.uploaded_at, a.size_bytes, a.is_latest,
                   s.owner_key, s.owner_label
            FROM artifact_uploads a
            INNER JOIN artifact_slugs s ON s.slug = a.slug
            WHERE s.owner_key = ? AND a.is_latest = 1
            ORDER BY a.uploaded_at DESC
            LIMIT ?
            """,
            (owner_key.strip(), limit),
        ).fetchall()
        return [_row_to_dict(row) for row in rows]
    finally:
        conn.close()


def list_uploads(
    db_file: Path,
    *,
    owner_key: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    if owner_key:
        return list_mine(db_file, owner_key=owner_key, limit=limit)
    conn = _connect(db_file)
    try:
        rows = conn.execute(
            """
            SELECT uuid, sha256, slug, title, uploaded_by, uploaded_at, size_bytes, is_latest
            FROM artifact_uploads
            ORDER BY uploaded_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [_row_to_dict(row) for row in rows]
    finally:
        conn.close()


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    data = {
        "uuid": row["uuid"],
        "sha256": row["sha256"],
        "slug": row["slug"],
        "title": row["title"],
        "uploaded_by": row["uploaded_by"],
        "uploaded_at": row["uploaded_at"],
        "size_bytes": row["size_bytes"],
        "is_latest": bool(row["is_latest"]),
    }
    keys = row.keys()
    if "owner_key" in keys:
        data["owner_key"] = row["owner_key"]
    if "owner_label" in keys:
        data["owner_label"] = row["owner_label"]
    if "source" in keys:
        data["source"] = row["source"]
    if "slack_user_id" in keys:
        data["slack_user_id"] = row["slack_user_id"]
    return data


def default_db_file(data_dir: Path | None = None) -> Path:
    return db_path(data_dir)
