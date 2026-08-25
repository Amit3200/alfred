"""Per-channel persona and docs-search routing."""

from __future__ import annotations

from pathlib import Path

from backend.db.slack_workflows_db import db_create_board_binding
from backend.models.config import AlfredConfig, RepoKnowledgeConfig, RoutingConfig
from backend.models.task import Task
from backend.routing.channel_settings import (
    channel_persona_system_block,
    should_force_channel_docs_search,
)
from backend.routing.tool_planner import _build_planner_channel_context, resolve_tool_plan
from backend.routing.types import RouteContext, RouteMode


def _task(text: str, *, channel: str = "Cdocs") -> Task:
    return Task(
        source="slack",
        user_id="U1",
        channel_id=channel,
        thread_ts="1.0",
        raw_text=text,
        cleaned_intent=text,
    )


def test_channel_persona_prepended_in_planner_context(tmp_path: Path):
    db_create_board_binding(
        tmp_path,
        board_key="support",
        list_id="Fdocs",
        channel_id="Cdocs",
        persona_prompt="This is billing support. Prefer invoice docs.",
        docs_search_enabled=True,
    )
    config = AlfredConfig()
    block = channel_persona_system_block(tmp_path, "Cdocs")
    assert "billing support" in block
    context = _build_planner_channel_context(config, _task("how does upsell work?"), tmp_path)
    assert "Channel persona" in context
    assert "invoice docs" in context
    assert "Docs search is ON" in context


def test_force_docs_search_skips_board_writes(tmp_path: Path):
    db_create_board_binding(
        tmp_path,
        board_key="support",
        list_id="Fdocs",
        channel_id="Cdocs",
        docs_search_enabled=True,
    )
    config = AlfredConfig(repo_knowledge=RepoKnowledgeConfig(enabled=True))
    assert should_force_channel_docs_search(
        _task("how do we configure upselling?"), tmp_path, config=config
    )
    assert not should_force_channel_docs_search(
        _task("create a task for checkout timeout"), tmp_path, config=config
    )


def test_resolve_tool_plan_uses_channel_docs_search(tmp_path: Path):
    db_create_board_binding(
        tmp_path,
        board_key="support",
        list_id="Fdocs",
        channel_id="Cdocs",
        docs_search_enabled=True,
    )
    config = AlfredConfig(
        repo_knowledge=RepoKnowledgeConfig(enabled=True),
        routing=RoutingConfig(tool_planner_enabled=True),
    )
    task = _task("what is upselling?")
    plan = resolve_tool_plan(
        config,
        task,
        RouteContext(
            intent=task.cleaned_intent,
            channel_id=task.channel_id,
            repo="",
            mode=RouteMode.INVESTIGATION,
        ),
        skill_allowed=["search_repo_docs", "read_repo_doc"],
        data_dir=tmp_path,
    )
    assert plan is not None
    assert plan.intent_class == "repo.docs.qa"
    assert "search_repo_docs" in plan.tools_needed
