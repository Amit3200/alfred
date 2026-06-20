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


def bundled_playbooks_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "docs" / "playbooks"


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
