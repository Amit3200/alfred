"""Tests for BM25 skill routing tier."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from backend.models.config import AlfredConfig, SkillsConfig
from backend.routing import RouteContext, RouteMode, SkillRouter
from backend.routing.bm25 import route_by_bm25
from backend.routing.playbooks import PlaybookStore


def _write_playbook(tmp_path: Path, name: str, *, triggers: list[str], description: str, body: str = "body") -> None:
    playbooks = tmp_path / "playbooks"
    playbooks.mkdir(exist_ok=True)
    trigger_yaml = "\n".join(f"  - {t}" for t in triggers)
    (playbooks / f"{name}.md").write_text(
        f"""---
name: {name}
mode: investigation
description: {description}
triggers:
{trigger_yaml}
allowed_tools: [grep_repo]
---
{body}
""",
        encoding="utf-8",
    )


def test_bm25_matches_description_when_keyword_misses(tmp_path: Path, monkeypatch):
    empty_skills = tmp_path / "empty_skills"
    empty_skills.mkdir()
    monkeypatch.setattr("backend.routing.playbooks.bundled_skills_dir", lambda: empty_skills)

    _write_playbook(
        tmp_path,
        "google_workspace",
        triggers=["google sheet export"],
        description="Create and update Google Docs and Sheets for the team",
    )
    store = PlaybookStore(tmp_path)
    config = AlfredConfig(skills=SkillsConfig(bm25_min_score=-1.0, bm25_min_gap=0.1))
    decision = route_by_bm25(
        RouteContext(intent="dump this summary into a google document please", mode=RouteMode.INVESTIGATION),
        store,
        config,
    )
    assert decision.strategy == "bm25"
    assert decision.skill_name == "google_workspace"


def test_bm25_rejects_ambiguous_scores(tmp_path: Path):
    _write_playbook(tmp_path, "skill_a", triggers=["payment"], description="payment webhook failures")
    _write_playbook(tmp_path, "skill_b", triggers=["payment"], description="payment checkout webhook errors")
    store = PlaybookStore(tmp_path)
    config = AlfredConfig(skills=SkillsConfig(bm25_min_score=0.5, bm25_min_gap=5.0))
    decision = route_by_bm25(
        RouteContext(intent="payment webhook error in checkout", mode=RouteMode.INVESTIGATION),
        store,
        config,
    )
    assert decision.skill_name is None
    assert "ambiguous" in decision.reason.lower()


def test_hybrid_bm25_wins_before_llm(tmp_path: Path, monkeypatch):
    empty_skills = tmp_path / "empty_skills"
    empty_skills.mkdir()
    monkeypatch.setattr("backend.routing.playbooks.bundled_skills_dir", lambda: empty_skills)

    _write_playbook(
        tmp_path,
        "google_workspace",
        triggers=["google sheet export"],
        description="Google Docs and Sheets read write tools",
    )
    store = PlaybookStore(tmp_path)
    provider = MagicMock()
    provider.is_available.return_value = True
    provider.chat.return_value = MagicMock(
        content='{"skill": "investigate_bug", "confidence": 0.99, "reason": "wrong"}'
    )
    llm_router = MagicMock()
    llm_router.resolve_task.return_value = ("kimi", provider, "m")

    config = AlfredConfig(skills=SkillsConfig(bm25_min_score=-1.0, bm25_min_gap=0.1))
    router = SkillRouter(config, store, llm_router=llm_router)
    result = router.route_investigation(
        RouteContext(intent="please put this in a google doc", mode=RouteMode.INVESTIGATION)
    )
    assert result.decision.strategy == "bm25"
    assert result.playbook is not None
    assert result.playbook.name == "google_workspace"
    provider.chat.assert_not_called()
