"""Phase 3 — repo doc index, plan-first routing, formatters, script triggers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from backend.context.doc_index import build_doc_index, search_repo_docs
from backend.formatting.intent_formatters import format_doc_search, format_reply_for_intent
from backend.integrations.company_scripts.manifest import parse_triggers
from backend.models.config import AlfredConfig, GitConfig, RepoKnowledgeConfig, RoutingConfig
from backend.models.task import Task
from backend.routing.entity_extractor import extract_entities
from backend.routing.playbooks import PlaybookStore
from backend.routing.tool_planner import plan_tools_rules


def test_parse_script_triggers():
    assert parse_triggers({"triggers": ["redirect metrics", "daily report"]}) == [
        "redirect metrics",
        "daily report",
    ]
    assert parse_triggers({"trigger_phrases": "run redirect"}) == ["run redirect"]


def test_doc_index_search(tmp_path: Path, monkeypatch):
    empty_skills = tmp_path / "empty_skills"
    empty_skills.mkdir()
    monkeypatch.setattr("backend.routing.playbooks.bundled_skills_dir", lambda: empty_skills)

    git = GitConfig(enabled=True, provider="github", token="t", main_repo="Acme/docs")
    mirror = tmp_path / "repos" / "shared" / "Acme__docs"
    docs_dir = mirror / "docs"
    docs_dir.mkdir(parents=True)
    (docs_dir / "redirect-runbook.md").write_text(
        "# Redirect runbook\n\nWhen redirect fails, check the edge cache and purge CDN keys.\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "backend.context.doc_index.shared_mirror_path",
        lambda data_dir, slug: mirror,
    )
    monkeypatch.setattr(
        "backend.context.generator._head_sha",
        lambda _mirror: "abc123",
    )
    monkeypatch.setattr(
        "backend.context.doc_index._collect_playbook_docs",
        lambda _data_dir: [],
    )

    manifest = build_doc_index(tmp_path, git, config=RepoKnowledgeConfig())
    assert manifest["chunk_count"] >= 1

    hits = search_repo_docs(tmp_path, "Acme/docs", "redirect edge cache")
    assert hits
    assert any("redirect-runbook" in h["path"] for h in hits)


def test_repo_docs_qa_tool_plan():
    task = Task(
        source="ui",
        user_id="u1",
        channel_id="c1",
        raw_text="what does the redirect runbook say about CDN",
        cleaned_intent="what does the redirect runbook say about CDN",
    )
    entities = extract_entities(task.cleaned_intent, task.raw_text, "")
    plan = plan_tools_rules(task, entities, skill_allowed=["search_repo_docs", "read_repo_doc"])
    assert plan is not None
    assert plan.intent_class == "repo.docs.qa"
    assert "search_repo_docs" in plan.tools_needed


def test_plan_first_resolves_skill_from_tool_plan(tmp_path: Path, monkeypatch):
    empty_skills = tmp_path / "empty_skills"
    empty_skills.mkdir()
    monkeypatch.setattr("backend.routing.playbooks.bundled_skills_dir", lambda: empty_skills)

    playbooks = tmp_path / "playbooks"
    playbooks.mkdir(exist_ok=True)
    (playbooks / "repo_knowledge.md").write_text(
        """---
name: repo_knowledge
mode: investigation
description: docs
triggers: []
allowed_tools: [search_repo_docs, read_repo_doc]
---
body
""",
        encoding="utf-8",
    )

    from backend.orchestrator.processor import TaskProcessor
    from backend.routing import RouteContext, RouteMode

    config = AlfredConfig(
        git=GitConfig(enabled=True, provider="github", token="ghp_test", main_repo="Acme/docs"),
        routing=RoutingConfig(
            plan_first_routing=True,
            skill_router_fallback=False,
            planner_strategy="rules_first",
        ),
    )
    processor = TaskProcessor(config)
    processor.router = MagicMock()
    processor.router.get.return_value = MagicMock(is_available=lambda: True)
    processor._playbooks = PlaybookStore(tmp_path)
    task = Task(
        source="ui",
        user_id="u1",
        channel_id="c1",
        raw_text="what does the redirect runbook say",
        cleaned_intent="what does the redirect runbook say",
    )
    ctx = RouteContext(intent=task.cleaned_intent, mode=RouteMode.INVESTIGATION)
    skill = processor._resolve_investigation_skill(ctx, task)
    assert skill is not None
    assert skill.name == "repo_knowledge"


def test_format_doc_search_not_found():
    text = format_doc_search({"query": "missing topic", "results": []})
    assert "No documentation found" in text


def test_format_reply_for_doc_search():
    data = {
        "query": "redirect",
        "results": [{"path": "docs/runbook.md", "title": "Runbook", "excerpt": "purge CDN"}],
    }
    out = format_reply_for_intent(
        intent_class="repo.docs.qa",
        kind="doc_search",
        data=data,
        raw_text="",
    )
    assert "docs/runbook.md" in out


def test_match_script_by_trigger(tmp_path: Path):
    scripts_root = tmp_path / "scripts"
    pkg = scripts_root / "redirect_metrics"
    pkg.mkdir(parents=True)
    (pkg / "script.yaml").write_text(
        """
name: redirect_metrics
description: Redirect metrics job
triggers:
  - redirect metrics
entry: main.py
runtime: python3
""".strip(),
        encoding="utf-8",
    )
    (pkg / "main.py").write_text("print('ok')\n", encoding="utf-8")

    config = AlfredConfig()
    config.scripts.enabled = True
    from backend.integrations.company_scripts.triggers import match_script_by_trigger

    name = match_script_by_trigger("please run redirect metrics for today", data_dir=tmp_path, config=config)
    assert name == "redirect_metrics"
