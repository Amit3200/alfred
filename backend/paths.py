"""Resolve Alfred data directories and config file locations."""

from __future__ import annotations

import os
from pathlib import Path

ENV_DATA_DIR = "ALFRED_DATA_DIR"
DEFAULT_DIR_NAME = ".alfred"


def get_data_dir(explicit: Path | None = None) -> Path:
    """Return the Alfred data directory (created on first use)."""
    if explicit is not None:
        path = explicit.expanduser().resolve()
    elif env := os.environ.get(ENV_DATA_DIR):
        path = Path(env).expanduser().resolve()
    else:
        # Prefer ./.alfred in the current project when initialized (matches ./scripts/setup.sh).
        project_dir = (Path.cwd() / DEFAULT_DIR_NAME).resolve()
        if (project_dir / "config.yaml").exists():
            path = project_dir
        else:
            path = Path.home() / DEFAULT_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_path(data_dir: Path | None = None) -> Path:
    return get_data_dir(data_dir) / "config.yaml"


def secrets_path(data_dir: Path | None = None) -> Path:
    return get_data_dir(data_dir) / "secrets.enc"


def key_path(data_dir: Path | None = None) -> Path:
    return get_data_dir(data_dir) / ".key"


def db_path(data_dir: Path | None = None) -> Path:
    return get_data_dir(data_dir) / "alfred.db"


def log_path(data_dir: Path | None = None) -> Path:
    return get_data_dir(data_dir) / "alfred.log"


def playbooks_dir(data_dir: Path | None = None) -> Path:
    return get_data_dir(data_dir) / "playbooks"


def company_scripts_dir(data_dir: Path | None = None) -> Path:
    """Local company script overrides — `.alfred/scripts/`."""
    return get_data_dir(data_dir) / "scripts"


def scripts_venv_dir(data_dir: Path | None = None) -> Path:
    """Isolated venv for remote script package dependencies."""
    return get_data_dir(data_dir) / "scripts-venv"


def scripts_sync_state_path(data_dir: Path | None = None) -> Path:
    return get_data_dir(data_dir) / "scripts-sync.json"


def bundled_playbooks_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "docs" / "playbooks"


def bundled_scripts_examples_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "docs" / "scripts" / "examples"


def bundled_skills_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "skills"


def exports_dir(data_dir: Path | None = None) -> Path:
    path = get_data_dir(data_dir) / "exports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def run_dir(data_dir: Path | None = None) -> Path:
    """Runtime PID/state files for background `alfred up`."""
    path = get_data_dir(data_dir) / "run"
    path.mkdir(parents=True, exist_ok=True)
    return path


def repos_dir(data_dir: Path | None = None) -> Path:
    """Root for git mirrors (shared + per-session workspaces)."""
    path = get_data_dir(data_dir) / "repos"
    path.mkdir(parents=True, exist_ok=True)
    return path


def shared_repos_dir(data_dir: Path | None = None) -> Path:
    path = repos_dir(data_dir) / "shared"
    path.mkdir(parents=True, exist_ok=True)
    return path


def workspace_repos_root(data_dir: Path | None = None) -> Path:
    path = repos_dir(data_dir) / "workspaces"
    path.mkdir(parents=True, exist_ok=True)
    return path


def context_dir(data_dir: Path | None = None) -> Path:
    """Generated repo context markdown under .alfred/context/."""
    path = get_data_dir(data_dir) / "context"
    path.mkdir(parents=True, exist_ok=True)
    return path


def repo_context_dir(data_dir: Path | None, repo_slug: str) -> Path:
    """Per-repo context output: .alfred/context/{owner__name}/."""
    safe = repo_slug.replace("/", "__")
    path = context_dir(data_dir) / safe
    path.mkdir(parents=True, exist_ok=True)
    return path


def branding_dir(data_dir: Path | None = None) -> Path:
    path = get_data_dir(data_dir) / "branding"
    path.mkdir(parents=True, exist_ok=True)
    return path


def artifacts_dir(data_dir: Path | None = None) -> Path:
    """Content-addressed HTML presentations under `.alfred/artifacts/`."""
    path = get_data_dir(data_dir) / "artifacts"
    path.mkdir(parents=True, exist_ok=True)
    return path


def artifact_blobs_dir(data_dir: Path | None = None) -> Path:
    path = artifacts_dir(data_dir) / "blobs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def artifact_blob_path(data_dir: Path, sha256: str) -> Path:
    """Two-level shard layout: blobs/ab/abcdef....html"""
    digest = sha256.lower().strip()
    return artifact_blobs_dir(data_dir) / digest[:2] / f"{digest}.html"


def bundled_artifacts_static_dir() -> Path:
    """Bundled logos and reference templates shipped with Alfred."""
    return Path(__file__).resolve().parent / "static" / "artifacts"


def bundled_web_dist() -> Path | None:
    """Return path to bundled admin UI static assets, if present."""
    package_root = Path(__file__).resolve().parent
    candidates = [
        package_root / "static" / "admin",
        Path.cwd() / "frontend" / "dist",
    ]
    for candidate in candidates:
        if (candidate / "index.html").exists():
            return candidate
    return None
