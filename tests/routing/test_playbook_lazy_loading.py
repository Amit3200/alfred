"""Tests for lazy skill loading and shared PlaybookStore registry."""

from __future__ import annotations

from pathlib import Path

from backend.routing.playbook_store_registry import (
    get_playbook_store,
    invalidate_playbook_store,
    reset_playbook_store_registry,
)
from backend.routing.playbooks import PlaybookStore


def _isolated_store(tmp_path: Path, monkeypatch) -> PlaybookStore:
    empty_skills = tmp_path / "empty_bundled_skills"
    empty_skills.mkdir()
    monkeypatch.setattr("backend.routing.playbooks.bundled_skills_dir", lambda: empty_skills)
    return PlaybookStore(tmp_path)


def test_list_playbooks_indexes_without_loading_bodies(tmp_path: Path, monkeypatch) -> None:
    playbooks = tmp_path / "playbooks"
    playbooks.mkdir()
    (playbooks / "lazy.md").write_text(
        """---
name: lazy-skill
triggers:
  - lazy-test
---

Full body should not load during routing.
""",
        encoding="utf-8",
    )
    store = _isolated_store(tmp_path, monkeypatch)
    indexed = store.list_playbooks()
    assert len(indexed) == 1
    assert indexed[0].body_loaded is False
    assert indexed[0].name == "lazy-skill"

    prompt = store.format_for_prompt(indexed)
    assert indexed[0].body_loaded is True
    assert "Full body should not load during routing." in prompt


def test_shared_store_is_singleton_per_data_dir(tmp_path: Path) -> None:
    reset_playbook_store_registry()
    first = get_playbook_store(tmp_path)
    second = get_playbook_store(tmp_path)
    assert first is second


def test_invalidate_playbook_store_reloads_index(tmp_path: Path, monkeypatch) -> None:
    reset_playbook_store_registry()
    empty_skills = tmp_path / "empty_bundled_skills"
    empty_skills.mkdir()
    monkeypatch.setattr("backend.routing.playbooks.bundled_skills_dir", lambda: empty_skills)
    playbooks = tmp_path / "playbooks"
    playbooks.mkdir()
    path = playbooks / "one.md"
    path.write_text(
        """---
name: one
triggers:
  - alpha
---
v1
""",
        encoding="utf-8",
    )
    store = get_playbook_store(tmp_path)
    assert store.get_by_name("one") is not None

    path.write_text(
        """---
name: one
triggers:
  - alpha
---
v2
""",
        encoding="utf-8",
    )
    invalidate_playbook_store(tmp_path)
    playbook = store.get_by_name("one")
    assert playbook is not None
    assert playbook.body == "v2"


def test_disabled_skills_update_on_shared_store(tmp_path: Path) -> None:
    reset_playbook_store_registry()
    store = get_playbook_store(tmp_path, disabled_skills=["investigate_bug"])
    assert "investigate_bug" in store.disabled_skills

    get_playbook_store(tmp_path, disabled_skills=[])
    assert store.disabled_skills == set()
