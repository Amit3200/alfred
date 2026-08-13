"""Filesystem + SQLite store for HTML presentation artifacts."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from backend.db import artifacts_db
from backend.paths import artifact_blob_path, artifact_blobs_dir

MAX_HTML_BYTES = 10 * 1024 * 1024
_HTML_DOCTYPE_RE = re.compile(r"<!doctype\s+html", re.IGNORECASE)


class ArtifactStore:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.db_file = artifacts_db.default_db_file(data_dir)
        artifact_blobs_dir(data_dir)

    def save_html(
        self,
        content: bytes,
        *,
        slug: str = "",
        title: str = "",
        uploaded_by: str = "admin",
        owner_key: str = "",
        source: str = "api",
        slack_user_id: str = "",
    ) -> dict[str, Any]:
        if not content:
            raise ValueError("HTML content is empty")
        if len(content) > MAX_HTML_BYTES:
            raise ValueError(f"HTML exceeds {MAX_HTML_BYTES // (1024 * 1024)} MB limit")
        text_head = content[:512].decode("utf-8", errors="ignore")
        if not _HTML_DOCTYPE_RE.search(text_head) and "<html" not in text_head.lower():
            raise ValueError("Content must be HTML (expected <!DOCTYPE html> or <html>)")

        digest = hashlib.sha256(content).hexdigest()
        blob_path = artifact_blob_path(self.data_dir, digest)
        if not blob_path.exists():
            blob_path.parent.mkdir(parents=True, exist_ok=True)
            blob_path.write_bytes(content)

        slug_clean = slug.strip()
        if slug_clean:
            meta = artifacts_db.record_upload(
                self.db_file,
                sha256=digest,
                slug=slug_clean,
                title=title,
                uploaded_by=uploaded_by,
                owner_key=owner_key or uploaded_by,
                source=source,
                slack_user_id=slack_user_id,
                size_bytes=len(content),
            )
        else:
            meta = artifacts_db.record_sha_upload(
                self.db_file,
                sha256=digest,
                title=title,
                uploaded_by=uploaded_by,
                owner_key=owner_key or uploaded_by,
                source=source,
                slack_user_id=slack_user_id,
                size_bytes=len(content),
            )
        meta["blob_path"] = str(blob_path)
        meta["publish_mode"] = "slug" if slug_clean else "sha"
        return meta

    def blob_path_for_sha(self, sha256: str) -> Path | None:
        path = artifact_blob_path(self.data_dir, sha256)
        return path if path.is_file() else None

    def blob_path_for_slug(self, slug: str) -> Path | None:
        meta = artifacts_db.get_latest_by_slug(self.db_file, slug)
        if not meta:
            return None
        return self.blob_path_for_sha(meta["sha256"])

    def get_latest_meta(self, slug: str) -> dict[str, Any] | None:
        return artifacts_db.get_latest_by_slug(self.db_file, slug)

    def get_meta_by_sha(self, sha256: str) -> dict[str, Any] | None:
        return artifacts_db.get_by_sha(self.db_file, sha256)

    def list_versions(self, slug: str) -> list[dict[str, Any]]:
        return artifacts_db.list_versions(self.db_file, slug)

    def get_slug_owner(self, slug: str) -> dict[str, Any] | None:
        return artifacts_db.get_slug_owner(self.db_file, slug)

    def user_owns_slug(self, slug: str, owner_key: str) -> bool:
        owner = self.get_slug_owner(slug)
        if owner is None:
            return False
        return owner["owner_key"] == owner_key.strip()

    def list_mine(self, *, owner_key: str, limit: int = 100) -> list[dict[str, Any]]:
        return artifacts_db.list_mine(self.db_file, owner_key=owner_key, limit=limit)

    def list_uploads(
        self,
        *,
        owner_key: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        return artifacts_db.list_uploads(
            self.db_file,
            owner_key=owner_key,
            limit=limit,
        )
