"""LangGraph orchestration tests (Phase 2b)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from backend.models.config import AlfredConfig, RoutingConfig
from backend.orchestrator.graph.build import build_alfred_graph, get_compiled_graph
from backend.orchestrator.graph.serialize import tool_plan_from_dict, tool_plan_to_dict
from backend.orchestrator.graph.skill_policy import resolve_policy_skill
from backend.routing.playbooks import Playbook, PlaybookStore
from backend.routing.tool_plan_types import ToolPlan, ToolPlanStep
from backend.routing.types import RouteContext, RouteMode


def test_build_alfred_graph_compiles():
    compiled = get_compiled_graph(False)
    assert compiled is not None
    graph = build_alfred_graph()
    assert graph is not None


def test_tool_plan_roundtrip():
    plan = ToolPlan(
        goal="Create sheet",
        confidence=0.9,
        tools_needed=["google_create_sheet"],
        intent_class="google.create.sheet",
    )
    restored = tool_plan_from_dict(tool_plan_to_dict(plan))
    assert restored is not None
    assert restored.tools_needed == ["google_create_sheet"]


def test_resolve_policy_skill_from_intent():
    store = PlaybookStore()
    plan = ToolPlan(
        goal="x",
        confidence=0.9,
        tools_needed=["jira_search"],
        intent_class="jira.read",
    )
    fallback = store.get_by_name("investigate_bug")
    skill = resolve_policy_skill(plan, store, fallback=fallback)
    assert skill is not None
    assert skill.name in ("jira_management", "jira_ticket", "investigate_bug")


def test_langgraph_investigation_routes_direct():
    from backend.models.task import Task
    from backend.orchestrator.processor import TaskProcessor
    from backend.models.config import GitConfig, default_config

    config = default_config()
    config.routing = RoutingConfig(langgraph_enabled=True, langgraph_checkpoint=False)
    config.git = GitConfig(enabled=True, provider="github", token="ghp_test")

    processor = TaskProcessor(config)
    processor.router = MagicMock()
    processor.router.get.return_value = MagicMock(is_available=lambda: True)

    from backend.routing.playbooks import PlaybookStore

    store = PlaybookStore()
    skill = store.get_by_name("git_status")
    assert skill is not None

    task = Task(
        source="slack",
        user_id="U1",
        channel_id="C1",
        raw_text="my open prs",
        cleaned_intent="my open prs",
    )
    route_context = RouteContext(intent=task.cleaned_intent, mode=RouteMode.INVESTIGATION)

    prs = [{"number": 1, "title": "Test", "state": "open", "repo": "a/b", "url": "http://x", "author": "u"}]
    mock_response = MagicMock()
    mock_response.payload.kind = "pr_list"
    mock_response.payload.data = {"prs": prs, "state": "open"}

    with patch(
        "backend.orchestrator.graph.nodes.resolve_tool_plan",
        return_value=ToolPlan(
            goal="List my PRs",
            confidence=0.95,
            tools_needed=["list_my_prs"],
            steps=[ToolPlanStep("list_my_prs", "list", {})],
            intent_class="git.read",
        ),
    ):
        with patch.object(processor, "_try_unified_direct", return_value=(mock_response, None)):
            with patch("backend.orchestrator.graph.nodes.run_agent_loop") as mock_loop:
                from backend.orchestrator.graph.runner import run_investigation_graph
                from backend.ai.base import Message

                response, patch_meta = run_investigation_graph(
                    processor,
                    skill,
                    [Message(role="user", content="my open prs")],
                    provider=MagicMock(),
                    model="test",
                    task=task,
                    session=None,
                    route_context=route_context,
                )
    assert response.payload.kind == "pr_list"
    mock_loop.assert_not_called()
