"""LLM-first tool planner routing."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from backend.models.config import AlfredConfig, RoutingConfig, SlackConfig
from backend.models.task import Task
from backend.orchestrator.graph.skill_policy import resolve_policy_skill
from backend.routing.playbook_store_registry import get_playbook_store
from backend.routing.tool_plan_types import ToolPlan
from backend.routing.tool_planner import (
    planner_llm_enabled,
    plan_tools_rules,
    resolve_tool_plan,
)
from backend.routing.types import RouteContext


def test_planner_llm_enabled_default():
    config = AlfredConfig()
    assert config.routing.planner_strategy == "llm_first"
    assert planner_llm_enabled(config)


def test_entity_direct_only_skips_phrase_rules():
    task = Task(
        source="slack",
        user_id="U1",
        channel_id="C1",
        raw_text="what does the redirect runbook say about CDN",
        cleaned_intent="what does the redirect runbook say about CDN",
    )
    from backend.routing.entity_extractor import extract_entities

    entities = extract_entities(task.cleaned_intent, task.raw_text, "")
    plan = plan_tools_rules(
        task,
        entities,
        skill_allowed=["search_repo_docs", "read_repo_doc"],
        entity_direct_only=True,
    )
    assert plan is None


def test_llm_first_prefers_llm_over_phrase_rules(tmp_path, monkeypatch):
    empty_skills = tmp_path / "empty_skills"
    empty_skills.mkdir()
    monkeypatch.setattr("backend.routing.playbooks.bundled_skills_dir", lambda: empty_skills)

    config = AlfredConfig(
        routing=RoutingConfig(planner_strategy="llm_first"),
        slack=SlackConfig(enabled=True),
    )
    task = Task(
        source="slack",
        user_id="U1",
        channel_id="C1",
        raw_text="can you see if this is configured to track and assign tasks?",
        cleaned_intent="can you see if this is configured to track and assign tasks?",
    )
    context = RouteContext(intent=task.cleaned_intent, channel_id=task.channel_id)

    provider = MagicMock()
    provider.chat.return_value = MagicMock(
        content=json.dumps(
            {
                "goal": "Check Slack board channel configuration",
                "confidence": 0.91,
                "tools_needed": [],
                "steps": [],
                "missing_capabilities": [],
                "intent_class": "slack.board.config",
            }
        )
    )

    plan = resolve_tool_plan(
        config,
        task,
        context,
        provider=provider,
        data_dir=tmp_path,
    )
    assert plan is not None
    assert plan.strategy == "llm"
    assert plan.intent_class == "slack.board.config"
    provider.chat.assert_called_once()

    playbooks = tmp_path / "playbooks"
    playbooks.mkdir()
    (playbooks / "slack_board_management.md").write_text(
        """---
name: slack_board_management
mode: investigation
description: Slack boards
triggers: []
allowed_tools: [slack_board_search_tasks]
---
body
""",
        encoding="utf-8",
    )
    store = get_playbook_store(tmp_path, disabled_skills=[])
    skill = resolve_policy_skill(plan, store, fallback=None, data_dir=tmp_path)
    assert skill is not None
    assert skill.name == "slack_board_management"


def test_plan_template_beats_llm_first(tmp_path, monkeypatch):
    playbooks = tmp_path / "playbooks"
    playbooks.mkdir()
    (playbooks / "daily_metrics_oneshot.md").write_text(
        """---
name: daily_metrics_oneshot
mode: workflow
type: plan_template
triggers:
  - run daily_metrics_oneshot
plan_template:
  goal: Run daily metrics and publish
  intent_class: template.daily_metrics_oneshot
  steps:
    - tool: run_company_script
      args: { script: daily_metrics_oneshot }
    - tool: publish_html_artifact
      args: { source_filename: daily-metrics-latest.html, slug: daily-metrics }
---
# body
""",
        encoding="utf-8",
    )
    empty_skills = tmp_path / "empty_skills"
    empty_skills.mkdir()
    monkeypatch.setattr("backend.routing.playbooks.bundled_skills_dir", lambda: empty_skills)
    monkeypatch.setattr("backend.routing.playbooks.playbooks_dir", lambda _data: playbooks)

    config = AlfredConfig(routing=RoutingConfig(planner_strategy="llm_first"))
    task = Task(
        source="scheduler",
        user_id="scheduler",
        channel_id="C1",
        raw_text="Run scheduled job daily_metrics_oneshot",
        cleaned_intent="run daily_metrics_oneshot",
    )
    context = RouteContext(intent=task.cleaned_intent, channel_id=task.channel_id)
    provider = MagicMock()
    provider.chat.return_value = MagicMock(
        content=json.dumps(
            {
                "goal": "Run a company script",
                "confidence": 0.99,
                "tools_needed": ["run_company_script"],
                "steps": [],
                "missing_capabilities": [],
                "intent_class": "script.run",
            }
        )
    )
    plan = resolve_tool_plan(
        config,
        task,
        context,
        provider=provider,
        playbook_store=get_playbook_store(tmp_path, disabled_skills=[]),
        data_dir=tmp_path,
    )
    assert plan is not None
    assert plan.strategy == "plan_template"
    assert plan.intent_class == "template.daily_metrics_oneshot"
    assert plan.tools_needed == ["run_company_script", "publish_html_artifact"]
    provider.chat.assert_not_called()


def test_create_schedule_beats_plan_template_and_llm(tmp_path, monkeypatch):
    playbooks = tmp_path / "playbooks"
    playbooks.mkdir()
    (playbooks / "daily_metrics_oneshot.md").write_text(
        """---
name: daily_metrics_oneshot
mode: workflow
type: plan_template
triggers:
  - daily metrics oneshot
plan_template:
  goal: Run daily metrics
  steps:
    - tool: run_company_script
      args: { script: daily_metrics_oneshot }
---
# body
""",
        encoding="utf-8",
    )
    empty_skills = tmp_path / "empty_skills"
    empty_skills.mkdir()
    monkeypatch.setattr("backend.routing.playbooks.bundled_skills_dir", lambda: empty_skills)
    monkeypatch.setattr("backend.routing.playbooks.playbooks_dir", lambda _data: playbooks)

    config = AlfredConfig(routing=RoutingConfig(planner_strategy="llm_first"))
    text = (
        "Create a schedule for 6 AM IST to call daily metrics oneshot "
        "the playbook is already created (daily_metrics_oneshot) "
        "HTML slides -> Slack\n0 6 * * *"
    )
    task = Task(
        source="ui",
        user_id="u1",
        channel_id="c1",
        raw_text=text,
        cleaned_intent=text,
    )
    context = RouteContext(intent=task.cleaned_intent, channel_id=task.channel_id)
    provider = MagicMock()
    plan = resolve_tool_plan(
        config,
        task,
        context,
        provider=provider,
        playbook_store=get_playbook_store(tmp_path, disabled_skills=[]),
        skill_allowed=["create_schedule", "list_schedules", "run_company_script"],
        data_dir=tmp_path,
    )
    assert plan is not None
    assert plan.tools_needed == ["create_schedule"]
    assert plan.intent_class == "schedule.write.create"
    assert plan.steps[0].args_hint["cron_expression"] == "0 6 * * *"
    assert plan.steps[0].args_hint["name"] == "daily_metrics_oneshot"
    provider.chat.assert_not_called()


def test_llm_first_doc_question_uses_search_tools(tmp_path):
    config = AlfredConfig(routing=RoutingConfig(planner_strategy="llm_first"))
    task = Task(
        source="ui",
        user_id="U1",
        channel_id="c1",
        raw_text="How do we configure Google Ads?",
        cleaned_intent="How do we configure Google Ads?",
    )
    context = RouteContext(intent=task.cleaned_intent, channel_id=task.channel_id)

    provider = MagicMock()
    provider.chat.return_value = MagicMock(
        content=json.dumps(
            {
                "goal": "Answer from repo docs",
                "confidence": 0.88,
                "tools_needed": ["search_repo_docs", "read_repo_doc"],
                "steps": [{"tool": "search_repo_docs", "purpose": "search docs"}],
                "missing_capabilities": [],
                "intent_class": "repo.docs.qa",
            }
        )
    )

    plan = resolve_tool_plan(
        config,
        task,
        context,
        provider=provider,
        skill_allowed=["search_repo_docs", "read_repo_doc"],
        data_dir=tmp_path,
    )
    assert plan is not None
    assert plan.intent_class == "repo.docs.qa"
    assert "search_repo_docs" in plan.tools_needed
