"""Pull company scripts (and optional playbooks) from a Git repository."""

from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.integrations.company_scripts.catalog import CompanyScriptStore
from backend.integrations.company_scripts.deps import ensure_scripts_venv, find_requirements_file
from backend.integrations.git.api import resolve_repo_slug
from backend.integrations.git.mirror import WorkspaceMirrorManager, _repo_dir_name
from backend.models.config import AlfredConfig
from backend.paths import playbooks_dir, scripts_sync_state_path

logger = logging.getLogger(__name__)


def sync_scripts_repository(
    config: AlfredConfig,
    data_dir: Path | None,
    *,
    checkout_branch: str | None = None,
) -> dict[str, Any]:
    """Clone/update scripts repo, install deps, optionally sync playbooks."""
    remote = config.scripts.remote
    if not remote.repo.strip():
        return {"ok": True, "skipped": True, "message": "scripts.remote.repo is not configured."}
    if not config.scripts.enabled:
        return {"ok": False, "message": "Company scripts are disabled (scripts.enabled: false)."}
    if not config.git.enabled:
        return {"ok": False, "message": "Git integration must be enabled to sync scripts.remote.repo."}
    if not (config.git.token or "").strip():
        return {"ok": False, "message": "Git token is required in Secrets to sync scripts.remote.repo."}

    branch = (checkout_branch or remote.branch or "main").strip() or "main"
    mirror = WorkspaceMirrorManager(config.git, _data_dir(data_dir))
    slug = resolve_repo_slug(remote.repo.strip(), config.git)
    dest = mirror.shared_root / _repo_dir_name(slug)

    try:
        if dest.is_dir() and (dest / ".git").exists():
            mirror._pull(dest, ref=branch)
            action = "updated"
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            mirror._clone(slug, dest, ref=branch)
            action = "cloned"
    except Exception as exc:
        logger.exception("Scripts repo sync failed for %s", slug)
        return {"ok": False, "repo": slug, "message": str(exc)}

    repo_root = dest
    subpath = remote.path.strip().strip("/")
    scripts_root = repo_root / subpath if subpath else repo_root
    if not scripts_root.is_dir():
        rel = scripts_root.relative_to(repo_root).as_posix() if subpath else "."
        return {"ok": False, "repo": slug, "message": f"Scripts path not found in repo: {rel}"}

    requirements_file = find_requirements_file(
        repo_root=repo_root,
        scripts_root=scripts_root,
        configured=remote.requirements_file,
    )
    deps_result = ensure_scripts_venv(config, data_dir, requirements_file=requirements_file)

    playbooks_result: dict[str, Any] | None = None
    if remote.playbooks_path.strip():
        playbooks_result = _sync_playbooks(
            repo_root=repo_root,
            playbooks_subpath=remote.playbooks_path.strip(),
            data_dir=data_dir,
            overwrite=remote.overwrite_local_playbooks,
        )

    CompanyScriptStore(data_dir, config=config).reload()

    state = {
        "repo": slug,
        "branch": branch,
        "action": action,
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "scripts_root": str(scripts_root),
        "requirements": str(requirements_file) if requirements_file else None,
        "python_mode": remote.python_mode,
        "deps": deps_result,
        "playbooks": playbooks_result,
    }
    _save_sync_state(data_dir, state)

    ok = deps_result.get("ok", True)
    return {
        "ok": ok,
        "repo": slug,
        "branch": branch,
        "action": action,
        "scripts_root": str(scripts_root),
        "scripts_path": scripts_root.relative_to(repo_root).as_posix() if subpath else ".",
        "requirements": str(requirements_file) if requirements_file else None,
        "python_mode": remote.python_mode,
        "python": deps_result.get("python"),
        "deps": deps_result,
        "playbooks": playbooks_result,
        "message": _format_sync_message(action, slug, deps_result, playbooks_result),
    }


def load_scripts_sync_state(data_dir: Path | None) -> dict[str, Any]:
    path = scripts_sync_state_path(data_dir)
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _sync_playbooks(
    *,
    repo_root: Path,
    playbooks_subpath: str,
    data_dir: Path | None,
    overwrite: bool,
) -> dict[str, Any]:
    source = repo_root / playbooks_subpath.strip("/")
    if not source.is_dir():
        return {"ok": False, "message": f"Playbooks path not found: {playbooks_subpath}"}
    dest = playbooks_dir(data_dir)
    dest.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    skipped: list[str] = []
    for path in sorted(source.rglob("*.md")):
        rel = path.relative_to(source)
        target = dest / rel
        if target.exists() and not overwrite:
            skipped.append(rel.as_posix())
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        copied.append(rel.as_posix())
    return {"ok": True, "copied": copied, "skipped": skipped, "count": len(copied)}


def _save_sync_state(data_dir: Path | None, state: dict[str, Any]) -> None:
    path = scripts_sync_state_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _format_sync_message(
    action: str,
    slug: str,
    deps_result: dict[str, Any],
    playbooks_result: dict[str, Any] | None,
) -> str:
    parts = [f"Scripts repo {slug} {action}."]
    if deps_result.get("skipped"):
        parts.append(str(deps_result.get("message") or ""))
    elif deps_result.get("ok"):
        parts.append(str(deps_result.get("message") or "Dependencies ready."))
    else:
        parts.append(str(deps_result.get("message") or "Dependency install failed."))
    if playbooks_result and playbooks_result.get("ok"):
        parts.append(f"Playbooks synced: {playbooks_result.get('count', 0)} file(s).")
    return " ".join(p for p in parts if p)


def _data_dir(data_dir: Path | None) -> Path:
    from backend.paths import get_data_dir

    return get_data_dir(data_dir)
