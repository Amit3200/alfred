"""Tests for doc Q&A LangGraph worker routing (Option B)."""

from __future__ import annotations

import json

from backend.orchestrator.graph.plan_routing import resolve_graph_route
from backend.routing.goal_spec import goal_spec_from_plan
from backend.routing.grounding_gate import ToolTraceEntry, validate_agent_result
from backend.routing.tool_plan_types import ToolPlan, ToolPlanStep


def test_doc_qa_plan_routes_to_worker_not_direct():
    plan = ToolPlan(
        goal="Answer from docs",
        confidence=0.97,
        tools_needed=["search_repo_docs", "read_repo_doc"],
        steps=[ToolPlanStep("search_repo_docs", "search", {"query": "bytespeed"})],
        intent_class="repo.docs.qa",
        strategy="persona",
    )
    assert resolve_graph_route(plan, allowed_tools=["search_repo_docs", "read_repo_doc"]) == "worker"


def test_single_step_non_doc_plan_still_direct():
    plan = ToolPlan(
        goal="List PRs",
        confidence=0.95,
        tools_needed=["list_my_prs"],
        steps=[ToolPlanStep("list_my_prs", "list", {})],
        intent_class="git.read",
    )
    assert resolve_graph_route(plan, allowed_tools=["list_my_prs"]) == "direct"


def test_goal_spec_for_doc_qa_requires_search_and_yes_no():
    plan = ToolPlan(
        goal="Answer from docs",
        confidence=0.97,
        tools_needed=["search_repo_docs", "read_repo_doc"],
        steps=[ToolPlanStep("search_repo_docs", "search", {})],
        intent_class="repo.docs.qa",
    )
    spec = goal_spec_from_plan(plan)
    assert spec is not None
    joined = " ".join(spec.success_criteria).lower()
    assert "search_repo_docs" in joined
    assert "yes or no" in joined


def test_doc_qa_grounding_rejects_answer_without_search():
    goal = goal_spec_from_plan(
        ToolPlan(
            goal="docs",
            confidence=0.9,
            tools_needed=["search_repo_docs"],
            intent_class="repo.docs.qa",
        )
    )
    result = validate_agent_result(
        "**Yes** — configure ByteSpeed in integrations.",
        [],
        goal,
    )
    assert not result.passed
    assert any("search_repo_docs" in issue for issue in result.issues)


def test_doc_qa_grounding_rejects_yes_when_search_empty():
    goal = goal_spec_from_plan(
        ToolPlan(
            goal="docs",
            confidence=0.9,
            tools_needed=["search_repo_docs"],
            intent_class="repo.docs.qa",
        )
    )
    trace = [
        ToolTraceEntry(
            tool="search_repo_docs",
            success=True,
            result_kind="doc_search",
            observation='{"query":"bytespeed","results":[],"found":false}',
        )
    ]
    result = validate_agent_result("**Yes** — ByteSpeed is supported.", trace, goal)
    assert not result.passed


def test_doc_qa_grounding_allows_checkout_url_after_read():
    goal = goal_spec_from_plan(
        ToolPlan(
            goal="docs",
            confidence=0.9,
            tools_needed=["search_repo_docs", "read_repo_doc"],
            intent_class="repo.docs.qa",
        )
    )
    doc_content = (
        "Open FlexyPe checkout in a webview: "
        "https://checkout.flexype.io/?session={session_id}"
    )
    trace = [
        ToolTraceEntry(
            tool="search_repo_docs",
            success=True,
            result_kind="doc_search",
            observation='{"found":true,"results":[{"path":"platforms/mobile-apps.mdx"}]}',
        ),
        ToolTraceEntry(
            tool="read_repo_doc",
            success=True,
            result_kind="doc_read",
            observation=(
                '{"kind":"doc_read","data":{"path":"platforms/mobile-apps.mdx",'
                f'"content":{json.dumps(doc_content)}}}'
            ),
        ),
    ]
    reply = (
        "**Yes** — FlexyPe supports mobile app checkout via webview. "
        "See `platforms/mobile-apps.mdx`."
    )
    result = validate_agent_result(reply, trace, goal)
    assert result.passed


def test_execute_planned_direct_skips_doc_qa(tmp_path):
    from backend.models.config import AlfredConfig, GitConfig, RepoKnowledgeConfig
    from backend.models.task import Task
    from backend.orchestrator.processor import TaskProcessor
    from backend.routing.chat_persona import build_support_doc_plan
    from backend.routing.playbook_store_registry import get_playbook_store

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
        raw_text="Do we have bytespeed integration?",
        cleaned_intent="Do we have bytespeed integration?",
    )
    plan = build_support_doc_plan(task)
    assert processor._execute_planned_direct(skill, task, None, plan) == (None, None)
