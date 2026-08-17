"""Public HTML artifact serving and admin upload API."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, HTMLResponse
from pydantic import BaseModel, Field

from backend.api.deps import get_artifact_actor, get_manager, require_admin
from backend.artifacts.actor import ArtifactActor
from backend.artifacts.store import ArtifactStore
from backend.config_manager import ConfigManager
from backend.db.artifacts_db import SlugOwnershipError

public_router = APIRouter(tags=["artifacts"])
admin_router = APIRouter(prefix="/artifacts", tags=["artifacts"])


class ArtifactUploadBody(BaseModel):
    html: str = Field(..., min_length=1)
    slug: str = Field(..., min_length=1, max_length=64)
    title: str = ""


def _store(manager: ConfigManager) -> ArtifactStore:
    return ArtifactStore(manager.data_dir)


def _public_urls(slug: str, sha256: str) -> dict[str, str]:
    return {
        "slug_url": f"/artifacts/s/{slug}",
        "sha_url": f"/artifacts/sha/{sha256}",
    }


def _enrich_meta(meta: dict[str, Any]) -> dict[str, Any]:
    urls = _public_urls(meta["slug"], meta["sha256"])
    return {
        **meta,
        **urls,
        "uploaded_at_iso": time.strftime(
            "%Y-%m-%dT%H:%M:%SZ",
            time.gmtime(meta["uploaded_at"]),
        ),
    }


def _assert_owner(store: ArtifactStore, slug: str, actor: ArtifactActor) -> None:
    owner = store.get_slug_owner(slug)
    if owner is None:
        return
    if owner["owner_key"] != actor.key:
        raise HTTPException(status_code=403, detail="You do not own this presentation slug")


def _serve_html_file(path, manager: ConfigManager) -> HTMLResponse:
    from backend.artifacts.html_deck import finalize_html_deck
    from backend.artifacts.slide_branding import build_slide_branding_context

    config, _ = manager.load_merged()
    html = path.read_text(encoding="utf-8")
    branding = build_slide_branding_context(config, manager.data_dir)
    return HTMLResponse(
        finalize_html_deck(html, branding=branding),
        media_type="text/html; charset=utf-8",
    )


@public_router.get("/artifacts/s/{slug}")
def serve_latest_by_slug(slug: str, manager: ConfigManager = Depends(get_manager)) -> HTMLResponse:
    """Public share link — no auth; anyone with the URL can view content."""
    store = _store(manager)
    path = store.blob_path_for_slug(slug)
    if path is None:
        raise HTTPException(status_code=404, detail="Presentation not found")
    return _serve_html_file(path, manager)


@public_router.get("/artifacts/sha/{sha256}")
def serve_by_sha(sha256: str, manager: ConfigManager = Depends(get_manager)) -> HTMLResponse:
    store = _store(manager)
    path = store.blob_path_for_sha(sha256)
    if path is None:
        raise HTTPException(status_code=404, detail="Presentation not found")
    return _serve_html_file(path, manager)


@admin_router.get("/mine")
def list_my_artifacts(
    limit: int = Query(default=100, ge=1, le=500),
    manager: ConfigManager = Depends(require_admin),
    actor: ArtifactActor = Depends(get_artifact_actor),
) -> dict[str, Any]:
    """Latest deck per owned slug for the current actor only."""
    store = _store(manager)
    rows = store.list_mine(owner_key=actor.key, limit=limit)
    return {
        "actor": {"key": actor.key, "label": actor.label},
        "artifacts": [_enrich_meta(row) for row in rows],
        "count": len(rows),
    }


@admin_router.get("/template/slides")
def get_slide_template() -> HTMLResponse:
    from backend.paths import bundled_artifacts_static_dir

    template_path = bundled_artifacts_static_dir() / "slide-template.html"
    if not template_path.is_file():
        raise HTTPException(status_code=404, detail="Template not found")
    return HTMLResponse(template_path.read_text(encoding="utf-8"))


@admin_router.get("/sha/{sha256}/meta")
def get_artifact_meta_by_sha(
    sha256: str,
    manager: ConfigManager = Depends(require_admin),
    actor: ArtifactActor = Depends(get_artifact_actor),
) -> dict[str, Any]:
    store = _store(manager)
    meta = store.get_meta_by_sha(sha256)
    if meta is None:
        raise HTTPException(status_code=404, detail="Presentation not found")
    _assert_owner(store, meta["slug"], actor)
    return {"artifact": _enrich_meta(meta)}


@admin_router.post("")
async def upload_artifact_json(
    body: ArtifactUploadBody,
    manager: ConfigManager = Depends(require_admin),
    actor: ArtifactActor = Depends(get_artifact_actor),
) -> dict[str, Any]:
    store = _store(manager)
    try:
        meta = store.save_html(
            body.html.encode("utf-8"),
            slug=body.slug,
            title=body.title,
            uploaded_by=actor.label,
            owner_key=actor.key,
        )
    except SlugOwnershipError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "artifact": _enrich_meta(meta)}


@admin_router.post("/upload")
async def upload_artifact_multipart(
    slug: str = Form(...),
    title: str = Form(""),
    file: UploadFile = File(...),
    manager: ConfigManager = Depends(require_admin),
    actor: ArtifactActor = Depends(get_artifact_actor),
) -> dict[str, Any]:
    content = await file.read()
    store = _store(manager)
    try:
        meta = store.save_html(
            content,
            slug=slug,
            title=title,
            uploaded_by=actor.label,
            owner_key=actor.key,
        )
    except SlugOwnershipError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "artifact": _enrich_meta(meta)}


@admin_router.get("/{slug}")
def get_artifact_meta(
    slug: str,
    manager: ConfigManager = Depends(require_admin),
    actor: ArtifactActor = Depends(get_artifact_actor),
) -> dict[str, Any]:
    store = _store(manager)
    _assert_owner(store, slug, actor)
    latest = store.get_latest_meta(slug)
    if latest is None:
        raise HTTPException(status_code=404, detail="Presentation not found")
    versions = store.list_versions(slug)
    return {
        "latest": _enrich_meta(latest),
        "versions": [_enrich_meta(v) for v in versions],
    }
