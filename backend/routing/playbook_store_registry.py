"""Process-level PlaybookStore registry — one cached store per Alfred data directory."""

from __future__ import annotations

from pathlib import Path

from backend.paths import get_data_dir
from backend.routing.playbooks import PlaybookStore

_registry: dict[str, PlaybookStore] = {}


def get_playbook_store(
    data_dir: Path | None = None,
    *,
    disabled_skills: list[str] | None = None,
) -> PlaybookStore:
    """Return the shared store for *data_dir*, creating it on first use."""
    key = str(get_data_dir(data_dir).resolve())
    store = _registry.get(key)
    if store is None:
        store = PlaybookStore(data_dir, disabled_skills=disabled_skills or [])
        _registry[key] = store
    elif disabled_skills is not None:
        store.set_disabled_skills(disabled_skills)
    return store


def invalidate_playbook_store(data_dir: Path | None = None) -> None:
    """Drop cached skill index so the next route reloads from disk."""
    key = str(get_data_dir(data_dir).resolve())
    store = _registry.get(key)
    if store is not None:
        store.reload()


def reset_playbook_store_registry() -> None:
    """Clear all stores — test helper."""
    _registry.clear()
