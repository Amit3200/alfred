"""Paths for company script catalogs (local + remote Git mirror)."""

from __future__ import annotations

from pathlib import Path

from backend.integrations.git.api import resolve_repo_slug
from backend.integrations.git.mirror import WorkspaceMirrorManager, _repo_dir_name
from backend.models.config import AlfredConfig
from backend.paths import company_scripts_dir, get_data_dir


def remote_scripts_root(config: AlfredConfig, data_dir: Path | None) -> Path | None:
    """Resolved scripts directory inside the synced remote repo mirror."""
    remote = config.scripts.remote
    if not remote.repo.strip() or not config.git.enabled:
        return None
    try:
        slug = resolve_repo_slug(remote.repo.strip(), config.git)
    except ValueError:
        return None
    repo_dir = WorkspaceMirrorManager(config.git, get_data_dir(data_dir)).shared_root / _repo_dir_name(slug)
    if not repo_dir.is_dir():
        return None
    subpath = remote.path.strip().strip("/")
    scripts_root = repo_dir / subpath if subpath else repo_dir
    return scripts_root if scripts_root.is_dir() else None


def remote_repo_root(config: AlfredConfig, data_dir: Path | None) -> Path | None:
    remote = config.scripts.remote
    if not remote.repo.strip() or not config.git.enabled:
        return None
    try:
        slug = resolve_repo_slug(remote.repo.strip(), config.git)
    except ValueError:
        return None
    repo_dir = WorkspaceMirrorManager(config.git, get_data_dir(data_dir)).shared_root / _repo_dir_name(slug)
    return repo_dir if repo_dir.is_dir() else None


def script_catalog_roots(data_dir: Path | None, *, config: AlfredConfig | None = None) -> list[Path]:
    """Remote repo scripts first; local `.alfred/scripts/` overrides on name collision."""
    roots: list[Path] = []
    if config is not None:
        remote_root = remote_scripts_root(config, data_dir)
        if remote_root is not None:
            roots.append(remote_root)
    roots.append(company_scripts_dir(data_dir))
    return roots
