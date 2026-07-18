"""Tests for investigation skill selection."""

from pathlib import Path

import pytest

from backend.routing.playbooks import PlaybookStore


@pytest.fixture
def isolated_store(tmp_path: Path, monkeypatch) -> PlaybookStore:
    empty_skills = tmp_path / "empty_bundled_skills"
    empty_skills.mkdir()
    playbooks = tmp_path / "playbooks"
    playbooks.mkdir()
    monkeypatch.setattr("backend.routing.playbooks.bundled_skills_dir", lambda: empty_skills)
    (playbooks / "review_pr.md").write_text(
        (Path(__file__).resolve().parents[1] / "skills" / "review_pr.md").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (playbooks / "git_status.md").write_text(
        (Path(__file__).resolve().parents[1] / "skills" / "git_status.md").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    return PlaybookStore(tmp_path)


def test_pick_investigation_prefers_review_pr_over_git_status(isolated_store: PlaybookStore):
    skill = isolated_store.pick_investigation(
        "please review pr https://github.com/org/repo/pull/1",
        channel_id="C1",
    )
    assert skill is not None
    assert skill.name == "review_pr"
    assert "get_pr_changes" in skill.allowed_tools
