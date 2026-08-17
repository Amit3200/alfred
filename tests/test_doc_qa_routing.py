"""Doc Q&A routing and direct execution tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from backend.context.doc_index import build_doc_index
from backend.models.config import AlfredConfig, GitConfig, GitRepoProfile, RepoKnowledgeConfig, RoutingConfig
from backend.models.task import Task
from backend.orchestrator.processor import TaskProcessor
from backend.routing.entity_extractor import extract_entities
from backend.routing.playbook_store_registry import get_playbook_store
from backend.routing.tool_planner import plan_tools_rules


def test_google_ads_integration_question_plans_doc_search():
    task = Task(
        source="ui",
        user_id="u1",
        channel_id="c1",
        raw_text="How google ads can be configured and integrated with FlexyPe?",
        cleaned_intent="How google ads can be configured and integrated with FlexyPe?",
    )
    entities = extract_entities(task.cleaned_intent, task.raw_text, "")
    plan = plan_tools_rules(task, entities, skill_allowed=["search_repo_docs", "read_repo_doc"])
    assert plan is not None
    assert plan.intent_class == "repo.docs.qa"
    assert plan.steps[0].tool == "search_repo_docs"


def test_upselling_about_question_plans_doc_search():
    from backend.routing.tool_planner import looks_like_repo_doc_question

    task = Task(
        source="ui",
        user_id="u1",
        channel_id="c1",
        raw_text="what is the upselling all about?",
        cleaned_intent="what is the upselling all about?",
    )
    assert looks_like_repo_doc_question(task.cleaned_intent)
    entities = extract_entities(task.cleaned_intent, task.raw_text, "")
    plan = plan_tools_rules(task, entities, skill_allowed=["search_repo_docs", "read_repo_doc"])
    assert plan is not None
    assert plan.intent_class == "repo.docs.qa"
    assert plan.steps[0].tool == "search_repo_docs"


def test_execute_repo_doc_qa_direct_answers_from_index(tmp_path: Path, monkeypatch):
    empty_skills = tmp_path / "empty_skills"
    empty_skills.mkdir()
    monkeypatch.setattr("backend.routing.playbooks.bundled_skills_dir", lambda: empty_skills)
    from shutil import copy

    copy(
        Path(__file__).resolve().parents[1] / "skills" / "repo_knowledge.md",
        empty_skills / "repo_knowledge.md",
    )

    mirror = tmp_path / "repos" / "shared" / "FlexyPe__docs"
    (mirror / "integrations" / "analytics").mkdir(parents=True)
    (mirror / "integrations" / "analytics" / "google-ads.mdx").write_text(
        "# Google Ads\n\nConnect Google Ads via the Analytics settings page and map conversion events.\n",
        encoding="utf-8",
    )

    git = GitConfig(
        enabled=True,
        default_org="FlexyPe",
        main_repo="FlexyPe/cipher",
        repo_profiles=[GitRepoProfile(repo="FlexyPe/docs", role="docs")],
    )
    config = AlfredConfig(
        git=git,
        repo_knowledge=RepoKnowledgeConfig(enabled=True),
        routing=RoutingConfig(tool_planner_enabled=True, langgraph_enabled=True),
    )

    monkeypatch.setattr(
        "backend.context.doc_index._collect_playbook_docs",
        lambda _data_dir: [],
    )
    build_doc_index(tmp_path, git, repo="FlexyPe/docs", alfred_config=config)

    store = get_playbook_store(tmp_path, disabled_skills=[])
    processor = TaskProcessor(config, data_dir=tmp_path, playbook_store=store)
    skill = store.get_by_name("repo_knowledge")
    assert skill is not None

    task = Task(
        source="ui",
        user_id="u1",
        channel_id="c1",
        raw_text="How google ads can be configured and integrated?",
        cleaned_intent="How google ads can be configured and integrated?",
    )

    mock_provider = MagicMock()
    mock_provider.chat.return_value = MagicMock(
        content="Configure Google Ads in Analytics settings and map conversion events. "
        "Source: integrations/analytics/google-ads.mdx"
    )

    with patch.object(processor, "_resolve_llm", return_value=("kimi", mock_provider, "test-model")):
        response, _patch = processor._execute_repo_doc_qa_direct(
            skill,
            task,
            None,
            task.cleaned_intent,
        )

    assert response is not None
    text = response.payload.data.get("text") or ""
    assert "google" in text.lower()
    assert "integrations/analytics/google-ads.mdx" in text.lower() or "analytics" in text.lower()


def test_execute_planned_direct_skips_doc_qa_for_worker(tmp_path: Path, monkeypatch):
    empty_skills = tmp_path / "empty_skills"
    empty_skills.mkdir()
    monkeypatch.setattr("backend.routing.playbooks.bundled_skills_dir", lambda: empty_skills)
    from shutil import copy

    copy(
        Path(__file__).resolve().parents[1] / "skills" / "repo_knowledge.md",
        empty_skills / "repo_knowledge.md",
    )

    config = AlfredConfig(
        git=GitConfig(enabled=True, default_org="FlexyPe", main_repo="FlexyPe/cipher"),
        repo_knowledge=RepoKnowledgeConfig(enabled=True),
    )
    store = get_playbook_store(tmp_path, disabled_skills=[])
    processor = TaskProcessor(config, data_dir=tmp_path, playbook_store=store)
    skill = store.get_by_name("repo_knowledge")
    assert skill is not None

    task = Task(
        source="ui",
        user_id="u1",
        channel_id="c1",
        raw_text="How do we configure Google Ads?",
        cleaned_intent="How do we configure Google Ads?",
    )
    plan = plan_tools_rules(task, extract_entities(task.cleaned_intent, task.raw_text, ""), skill_allowed=skill.allowed_tools)
    assert plan is not None

    direct = processor._execute_planned_direct(skill, task, None, plan)
    assert direct == (None, None)
