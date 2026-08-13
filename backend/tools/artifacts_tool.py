"""Tools for saving and optionally publishing HTML slide decks."""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

from backend.ai.base import ToolSchema
from backend.artifacts.store import ArtifactStore
from backend.db.artifacts_db import SlugOwnershipError
from backend.models.config import AlfredConfig
from backend.paths import exports_dir
from backend.tools.registry import ToolRegistry
from backend.tools.result import ToolResult

SAVE_HTML_DECK = ToolSchema(
    name="save_html_deck",
    description=(
        "Save a self-contained HTML slide deck to `.alfred/exports/` for download. "
        "Call ONLY after you have built the complete `<!DOCTYPE html>` document in the `html` argument. "
        "Never call with an empty `html` field. Use this by default for slide delivery — "
        "do NOT publish unless the user explicitly asks to host or share a URL."
    ),
    parameters={
        "type": "object",
        "properties": {
            "html": {
                "type": "string",
                "description": (
                    "Required. The full single-file HTML deck you generated "
                    "(<!DOCTYPE html> … </html>). Must not be empty."
                ),
            },
            "filename": {
                "type": "string",
                "description": "Optional filename ending in .html (e.g. q3-review.html).",
            },
        },
        "required": ["html"],
    },
)

PUBLISH_HTML_ARTIFACT = ToolSchema(
    name="publish_html_artifact",
    description=(
        "Upload HTML deck to Alfred artifact hosting for a public share link. "
        "ONLY call when the user explicitly asks to publish, host, upload, or share a link. "
        "With `slug`: stable URL at /artifacts/s/{slug} (latest version). "
        "Without `slug`: immutable URL at /artifacts/sha/{sha256}. "
        "Prefer `source_filename` from a prior save_html_deck export instead of re-passing `html`."
    ),
    parameters={
        "type": "object",
        "properties": {
            "html": {
                "type": "string",
                "description": "Complete single-file HTML with embedded images as data: URIs.",
            },
            "slug": {
                "type": "string",
                "description": (
                    "Optional stable URL slug (lowercase, hyphens), e.g. redirection-2025. "
                    "Omit for a content-addressed /artifacts/sha/{sha256} link only."
                ),
            },
            "source_filename": {
                "type": "string",
                "description": (
                    "Optional — load HTML from a prior save_html_deck export in `.alfred/exports/` "
                    "(e.g. presentation-1786635000.html) instead of passing `html` again."
                ),
            },
            "title": {
                "type": "string",
                "description": "Human-readable deck title.",
            },
            "uploaded_by": {
                "type": "string",
                "description": "Optional — auto-filled from Slack user or admin login when omitted.",
            },
            "owner_key": {
                "type": "string",
                "description": "Optional — auto-filled (slack:{user_id} or admin:{user}) when omitted.",
            },
        },
        "required": [],
    },
)

_SAFE_FILENAME_RE = re.compile(r"[^a-zA-Z0-9._-]+")


def _safe_html_filename(raw: str | None) -> str:
    name = (raw or "").strip() or f"presentation-{int(time.time())}.html"
    if not name.lower().endswith(".html"):
        name = f"{name}.html"
    name = _SAFE_FILENAME_RE.sub("-", name).strip("-")
    return name or "presentation.html"


def register_artifact_tools(
    registry: ToolRegistry,
    *,
    config: AlfredConfig,
    data_dir: Path | None,
) -> None:
    if data_dir is None:
        return

    def save_html_deck_handler(args: dict[str, Any]) -> ToolResult:
        from backend.artifacts.html_deck import finalize_html_deck, validate_html_deck
        from backend.artifacts.slide_branding import build_slide_branding_context

        html = str(args.get("html") or "")
        if not html.strip():
            return ToolResult.error(
                "html is required — build the complete <!DOCTYPE html> deck first, "
                "then call save_html_deck with the full HTML string in the `html` argument."
            )
        branding = build_slide_branding_context(config, data_dir)
        html = finalize_html_deck(html, branding=branding)
        issues = validate_html_deck(html)
        if issues:
            return ToolResult.error(
                "HTML deck is incomplete — "
                + "; ".join(issues)
                + ". Shorten slide copy or reduce slide count, then call save_html_deck again."
            )
        filename = _safe_html_filename(str(args.get("filename") or ""))
        try:
            dest = exports_dir(data_dir) / filename
            dest.write_text(html, encoding="utf-8")
        except OSError as exc:
            return ToolResult.error(f"Failed to save HTML deck: {exc}")
        return ToolResult(
            kind="html_deck_saved",
            data={
                "filename": filename,
                "path": str(dest),
                "download_url": f"/api/chat/exports/{filename}",
                "size_bytes": dest.stat().st_size,
            },
        )

    def publish_html_artifact_handler(args: dict[str, Any]) -> ToolResult:
        from backend.routing.html_slides_delivery import resolve_publish_html_args

        task = getattr(registry, "current_task", None)
        session_metadata = getattr(registry, "session_metadata", None)
        args = resolve_publish_html_args(
            args,
            task=task,
            session_metadata=session_metadata,
        )
        html = str(args.get("html") or "")
        slug = str(args.get("slug") or "").strip()
        source_filename = str(args.get("source_filename") or "").strip()
        if not html.strip() and source_filename:
            try:
                source_path = exports_dir(data_dir) / _safe_html_filename(source_filename)
                if source_path.is_file():
                    html = source_path.read_text(encoding="utf-8")
                else:
                    return ToolResult.error(
                        f"Saved deck not found: {source_filename} (looked in `.alfred/exports/`)."
                    )
            except OSError as exc:
                return ToolResult.error(f"Failed to read saved deck {source_filename}: {exc}")
        if not html.strip():
            return ToolResult.error(
                "html is required — pass the full HTML or `source_filename` from a prior save_html_deck export."
            )
        from backend.artifacts.html_deck import finalize_html_deck, validate_html_deck
        from backend.artifacts.slide_branding import build_slide_branding_context

        html = finalize_html_deck(html, branding=build_slide_branding_context(config, data_dir))
        issues = validate_html_deck(html)
        if issues:
            return ToolResult.error(
                "HTML deck is incomplete — "
                + "; ".join(issues)
                + ". Re-save the deck with complete HTML before publishing."
            )
        title = str(args.get("title") or "").strip()

        from backend.artifacts.actor import resolve_publish_actor
        from backend.artifacts.urls import artifact_public_url

        task = getattr(registry, "current_task", None)
        actor, source, slack_user_id = resolve_publish_actor(
            task=task,
            uploaded_by=str(args.get("uploaded_by") or ""),
            owner_key=str(args.get("owner_key") or ""),
        )
        public_base = ""
        alfred_config = getattr(registry, "alfred_config", None)
        if alfred_config is not None:
            public_base = (alfred_config.artifacts.public_base_url or "").strip()

        store = ArtifactStore(data_dir)
        try:
            meta = store.save_html(
                html.encode("utf-8"),
                slug=slug,
                title=title,
                uploaded_by=actor.label,
                owner_key=actor.key,
                source=source,
                slack_user_id=slack_user_id,
            )
        except SlugOwnershipError as exc:
            return ToolResult.error(str(exc))
        except ValueError as exc:
            return ToolResult.error(str(exc))

        slug_path = f"/artifacts/s/{meta['slug']}" if slug else ""
        sha_path = f"/artifacts/sha/{meta['sha256']}"
        primary_path = slug_path or sha_path
        publish_mode = "slug" if slug else "sha"
        return ToolResult(
            kind="html_artifact_published",
            data={
                "slug": meta.get("slug") if slug else "",
                "title": meta.get("title") or title,
                "sha256": meta["sha256"],
                "publish_mode": publish_mode,
                "slug_url": slug_path,
                "sha_url": sha_path,
                "share_url": artifact_public_url(public_base, primary_path),
                "uploaded_by": actor.label,
                "owner_key": actor.key,
                "source": source,
                "slack_user_id": slack_user_id,
            },
        )

    registry.register(SAVE_HTML_DECK, save_html_deck_handler)
    registry.register(PUBLISH_HTML_ARTIFACT, publish_html_artifact_handler)
