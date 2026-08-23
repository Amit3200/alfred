from backend.models.config import AlfredConfig, ConnectorsConfig, PeriskopeConfig, default_config
from backend.models.task import Task
from backend.orchestrator.graph.skill_policy import resolve_policy_skill
from backend.routing.connector_intent import build_connector_tool_plan, looks_like_connector_request
from backend.routing.playbooks import PlaybookStore
from backend.routing.tool_availability import playbook_has_runnable_tools
from backend.routing.tool_planner import resolve_tool_plan
from backend.routing.types import RouteContext


def _task(text: str, *, source: str = "ui") -> Task:
    return Task(
        source=source,  # type: ignore[arg-type]
        user_id="U1",
        channel_id="C1",
        thread_ts="1.0",
        raw_text=text,
        cleaned_intent=text,
    )


def test_looks_like_connector_request():
    assert looks_like_connector_request("@alfred list Periskope WhatsApp chats")
    assert looks_like_connector_request("poll Periskope preview only")
    assert looks_like_connector_request("is Periskope enabled? List connectors.")
    assert not looks_like_connector_request("how does merchant checkout work")


def test_build_connector_tool_plan_lists_chats():
    plan = build_connector_tool_plan(_task("list Periskope WhatsApp chats"))
    assert plan is not None
    assert plan.tools_needed == ["connector_list_chats"]
    assert plan.intent_class == "connector.read.chats"


def test_summarize_chats_for_a_date_fetches_messages():
    plan = build_connector_tool_plan(
        _task("list Periskope WhatsApp chats for 22nd August so far and summarise them for each channel")
    )
    assert plan is not None
    assert plan.tools_needed[0] == "connector_get_messages"
    assert "connector_list_chats" in plan.tools_needed


def test_last_week_summary_fetches_messages():
    plan = build_connector_tool_plan(
        _task("list Periskope WhatsApp chats and summarize context of each channel from last 1 week")
    )
    assert plan is not None
    assert plan.tools_needed[0] == "connector_get_messages"
    assert plan.steps[0].args_hint.get("start_time")


def test_connector_plan_beats_llm_first_without_provider():
    text = "list Periskope WhatsApp chats"
    task = _task(text)
    config = AlfredConfig()
    config.routing.planner_strategy = "llm_first"
    config.routing.tool_planner_enabled = True
    plan = resolve_tool_plan(
        config,
        task,
        RouteContext(intent=text),
        provider=None,
    )
    assert plan is not None
    assert plan.tools_needed == ["connector_list_chats"]


def test_summarize_query_beats_llm_first_without_provider():
    text = "list Periskope WhatsApp chats for 22nd August so far and summarise them for each channel"
    task = _task(text)
    config = AlfredConfig()
    config.routing.planner_strategy = "llm_first"
    config.routing.tool_planner_enabled = True
    plan = resolve_tool_plan(
        config,
        task,
        RouteContext(intent=text),
        provider=None,
    )
    assert plan is not None
    assert plan.tools_needed[0] == "connector_get_messages"
    assert "2026-08-22" in str(plan.steps[0].args_hint.get("start_time") or "")


def test_playbook_has_runnable_connector_tools_when_enabled():
    config = default_config()
    config.connectors = ConnectorsConfig(periskope=PeriskopeConfig(enabled=True))
    assert playbook_has_runnable_tools(["connector_list_chats", "jira_create_issue"], config)


def test_policy_skill_maps_connector_chats():
    store = PlaybookStore()
    plan = build_connector_tool_plan(_task("list Periskope WhatsApp chats"))
    skill = resolve_policy_skill(plan, store, fallback=None)
    assert skill is not None
    assert skill.name == "connector_management"


def test_pull_tickets_uses_list_tickets_not_poll():
    plan = build_connector_tool_plan(
        _task("can you pull all the tickets which has been created in the periskope?")
    )
    assert plan is not None
    assert plan.tools_needed == ["connector_list_tickets"]
    assert plan.intent_class == "connector.read.tickets"


def test_poll_preview_still_uses_connector_poll():
    plan = build_connector_tool_plan(_task("poll Periskope preview only"))
    assert plan is not None
    assert plan.tools_needed == ["connector_poll"]


def test_followup_tickets_ignores_prior_pull_in_raw_text():
    task = Task(
        source="ui",  # type: ignore[arg-type]
        user_id="U1",
        channel_id="C1",
        thread_ts="1.0",
        raw_text="I'll pull the WhatsApp chats\ncan you pull all the tickets which has been created in the periskope?",
        cleaned_intent="can you pull all the tickets which has been created in the periskope?",
    )
    plan = build_connector_tool_plan(task)
    assert plan is not None
    assert plan.tools_needed == ["connector_list_tickets"]


def test_screenshot_query_routes_to_worker():
    from backend.orchestrator.graph.plan_routing import resolve_graph_route

    plan = build_connector_tool_plan(
        _task("list Periskope WhatsApp chats for 22nd August so far and summarise them for each channel")
    )
    assert plan is not None
    assert resolve_graph_route(plan, allowed_tools=plan.tools_needed) == "worker"


def test_connector_skill_keeps_all_read_tools_on_turn():
    from unittest.mock import MagicMock

    from backend.routing.tool_plan_types import ToolPlan
    from backend.routing.tool_plan_validator import validate_tool_plan
    from backend.tools.registry import ToolRegistry

    registry = ToolRegistry()
    names = [
        "connector_list",
        "connector_list_chats",
        "connector_list_tickets",
        "connector_list_tasks",
        "connector_get_messages",
        "connector_poll",
    ]
    for name in names:
        registry._tools[name] = MagicMock()
    plan = ToolPlan(
        goal="List chats",
        confidence=0.9,
        tools_needed=["connector_list_chats"],
        intent_class="connector.read.chats",
    )
    binding = validate_tool_plan(
        plan,
        registry,
        skill_allowed=names,
        skill_name="connector_management",
    )
    assert "connector_get_messages" in binding.allowed_tools
    assert "connector_list_tickets" in binding.allowed_tools
