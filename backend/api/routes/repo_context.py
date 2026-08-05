"""Admin API for generated main-repo context."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from backend.api.deps import require_admin
from backend.config_manager import ConfigManager
from backend.context.generator import (
    context_status,
    generate_repo_context,
    load_repo_context_for_prompt,
    resolve_main_repo,
)
from backend.context.doc_index import doc_index_status
from backend.context.suggestions import (
    approve_suggestion,
    dismiss_suggestion,
    generate_suggestions,
    list_pending_suggestions,
)
from backend.context.graphify import (
    extract_graph,
    graph_detail,
    graph_summary,
    load_graph_report,
    record_graphify_build,
)
from backend.integrations.git.mirror import WorkspaceMirrorManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/repo-context", tags=["repo-context"])


def build_context_after_sync(
    manager: ConfigManager,
    *,
    sync_results: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Regenerate context and doc indexes for successfully synced repos."""
    config, _ = manager.load_merged()
    synced_ok = sorted({item["repo"] for item in sync_results if item.get("ok")})
    if not synced_ok:
        return None

    main = resolve_main_repo(config.git)
    repo_results: list[dict[str, Any]] = []
    manifest: dict[str, Any] | None = None

    for repo in synced_ok:
        entry: dict[str, Any] = {"repo": repo, "doc_index": False, "context": False}
        if config.repo_knowledge.enabled and config.repo_knowledge.index_on_sync:
            try:
                from backend.context.doc_index import build_doc_index

                build_doc_index(
                    manager.data_dir,
                    config.git,
                    repo=repo,
                    config=config.repo_knowledge,
                )
                entry["doc_index"] = True
            except Exception as exc:
                logger.warning("Doc index build failed for %s: %s", repo, exc)
                entry["doc_index_error"] = str(exc)
        repo_results.append(entry)

    if main and main in synced_ok:
        try:
            manifest = generate_repo_context(manager.data_dir, config.git, repo=main, ai=config.ai)
            for entry in repo_results:
                if entry["repo"] == main:
                    entry["context"] = True
        except Exception as exc:
            logger.warning("Repo context generation failed for %s: %s", main, exc)
            return {"ok": False, "error": str(exc), "repo": main, "repos": repo_results}

    pending = list_pending_suggestions(manager.data_dir, config.git) if main else []
    return {
        "ok": True,
        "manifest": manifest,
        "repos": repo_results,
        "suggestions_pending": len(pending),
    }


@router.get("")
def get_repo_context(manager: ConfigManager = Depends(require_admin)) -> dict[str, Any]:
    config, _ = manager.load_merged()
    status = context_status(manager.data_dir, config.git, ai=config.ai)
    preview = ""
    if status.get("configured") and config.git.enabled:
        preview = load_repo_context_for_prompt(manager.data_dir, config.git, max_chars=1200)
    pending = list_pending_suggestions(manager.data_dir, config.git)
    return {
        "status": status,
        "doc_index": doc_index_status(manager.data_dir, config),
        "preview": preview,
        "suggestions": pending,
    }


@router.post("/generate")
def regenerate_repo_context(manager: ConfigManager = Depends(require_admin)) -> dict[str, Any]:
    config, _ = manager.load_merged()
    if not config.git.enabled:
        raise HTTPException(status_code=400, detail="Git integration is disabled")
    main = resolve_main_repo(config.git)
    if not main:
        raise HTTPException(status_code=400, detail="git.main_repo is not configured")

    try:
        manifest = generate_repo_context(manager.data_dir, config.git, repo=main, ai=config.ai)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    pending = list_pending_suggestions(manager.data_dir, config.git)
    return {
        "ok": True,
        "manifest": manifest,
        "status": context_status(manager.data_dir, config.git, ai=config.ai),
        "suggestions": pending,
    }


@router.post("/sync-main")
def sync_main_repo_and_context(manager: ConfigManager = Depends(require_admin)) -> dict[str, Any]:
    """Sync shared mirror for main repo only, then regenerate context MD."""
    config, _ = manager.load_merged()
    if not config.git.enabled:
        raise HTTPException(status_code=400, detail="Git integration is disabled")
    if not config.git.token:
        raise HTTPException(status_code=400, detail="Git token is not configured")
    main = resolve_main_repo(config.git)
    if not main:
        raise HTTPException(status_code=400, detail="git.main_repo is not configured")

    mirror = WorkspaceMirrorManager(config.git, manager.data_dir)
    results = mirror.sync_shared([main])
    context_result = build_context_after_sync(manager, sync_results=results)
    pending = list_pending_suggestions(manager.data_dir, config.git)
    return {
        "ok": all(item.get("ok") for item in results),
        "sync_results": results,
        "context": context_result,
        "status": context_status(manager.data_dir, config.git, ai=config.ai),
        "suggestions": pending,
        "shared": mirror.list_shared(),
        "summary": mirror.storage_summary(),
    }


@router.get("/suggestions")
def get_suggestions(manager: ConfigManager = Depends(require_admin)) -> dict[str, Any]:
    config, _ = manager.load_merged()
    pending = list_pending_suggestions(manager.data_dir, config.git)
    return {"suggestions": pending}


@router.post("/suggestions/generate")
def create_suggestions(manager: ConfigManager = Depends(require_admin)) -> dict[str, Any]:
    config, _ = manager.load_merged()
    if not config.git.enabled:
        raise HTTPException(status_code=400, detail="Git integration is disabled")
    try:
        pending = generate_suggestions(manager.data_dir, config.git)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "suggestions": pending}


@router.post("/suggestions/{suggestion_id}/approve")
def approve_suggestion_route(
    suggestion_id: str,
    manager: ConfigManager = Depends(require_admin),
) -> dict[str, Any]:
    config, _ = manager.load_merged()
    try:
        result = approve_suggestion(manager.data_dir, config.git, suggestion_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result


@router.post("/suggestions/{suggestion_id}/dismiss")
def dismiss_suggestion_route(
    suggestion_id: str,
    manager: ConfigManager = Depends(require_admin),
) -> dict[str, Any]:
    config, _ = manager.load_merged()
    try:
        return dismiss_suggestion(manager.data_dir, config.git, suggestion_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/graphify")
def get_graphify_status(manager: ConfigManager = Depends(require_admin)) -> dict[str, Any]:
    config, _ = manager.load_merged()
    return graph_detail(manager.data_dir, config.git, ai=config.ai)


@router.get("/graphify/report")
def get_graphify_report(manager: ConfigManager = Depends(require_admin)) -> dict[str, Any]:
    config, _ = manager.load_merged()
    return load_graph_report(manager.data_dir, config.git)


@router.get("/graphify/summary")
def get_graphify_summary(manager: ConfigManager = Depends(require_admin)) -> dict[str, Any]:
    config, _ = manager.load_merged()
    main = resolve_main_repo(config.git)
    if not main:
        raise HTTPException(status_code=400, detail="git.main_repo is not configured")
    return graph_summary(manager.data_dir, main)


@router.post("/graphify/rebuild")
def rebuild_graphify(manager: ConfigManager = Depends(require_admin)) -> dict[str, Any]:
    """Rebuild Graphify graph from the shared mirror without re-syncing git."""
    config, _ = manager.load_merged()
    if not config.git.enabled:
        raise HTTPException(status_code=400, detail="Git integration is disabled")
    if not config.git.graphify_enabled:
        raise HTTPException(status_code=400, detail="Graphify is disabled in Integrations")
    main = resolve_main_repo(config.git)
    if not main:
        raise HTTPException(status_code=400, detail="git.main_repo is not configured")

    result = extract_graph(manager.data_dir, config.git, repo=main, ai=config.ai)
    if result.get("skipped"):
        raise HTTPException(status_code=400, detail=result.get("reason") or "Graphify skipped")
    record_graphify_build(manager.data_dir, main, result)
    status = graph_detail(manager.data_dir, config.git, ai=config.ai)
    return {
        "ok": bool(result.get("ok")),
        "result": result,
        "status": status,
    }
