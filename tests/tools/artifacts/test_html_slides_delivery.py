"""Tests for HTML slides delivery, planning, and grounding fixes."""

from __future__ import annotations

from backend.routing.entity_extractor import EntityBag
from backend.routing.goal_spec import goal_spec_from_plan
from backend.routing.grounding_gate import ToolTraceEntry, validate_agent_result
from backend.routing.html_slides_delivery import (
    build_html_slides_tool_plan,
    extract_export_filename_from_text,
    html_slides_system_addendum,
    html_slides_tool_manifest_addendum,
    inject_html_slides_bootstrap_message,
    looks_like_html_slides_followup,
    looks_like_html_slides_request,
    publish_args_complete,
    resolve_publish_html_args,
    salvage_html_deck_from_prose,
)
from backend.models.session import ConversationSession, ConversationTurn
from backend.routing.tool_plan_types import ToolPlan, ToolPlanStep
from backend.routing.tool_planner import plan_tools_rules, resolve_tool_plan
from backend.models.config import AlfredConfig
from backend.models.task import Task
from backend.routing.types import RouteContext, RouteMode
from backend.tools.artifacts.register import register_artifact_tools
from backend.tools.registry import ToolRegistry
from backend.config_manager import ConfigManager

from tests.slide_fixtures import MINIMAL_SLIDE_HTML

SAMPLE = MINIMAL_SLIDE_HTML


def test_looks_like_html_slides_request():
    assert looks_like_html_slides_request("create a presentation from this data")
    assert looks_like_html_slides_request("build html slides for Q3")
    assert not looks_like_html_slides_request("what is checkout redirect?")


def test_html_slides_plan_routes_to_worker_not_direct():
    from backend.orchestrator.graph.plan_routing import resolve_graph_route
    from backend.routing.tool_plan_types import ToolPlan, ToolPlanStep

    plan = ToolPlan(
        goal="Create deck",
        confidence=0.97,
        tools_needed=["save_html_deck"],
        steps=[ToolPlanStep("save_html_deck", "save deck")],
        intent_class="html_slides",
        strategy="rules",
    )
    assert resolve_graph_route(plan, allowed_tools=["save_html_deck"]) == "worker"


def test_execute_planned_direct_skips_save_html_deck(tmp_path):
    from backend.config_manager import ConfigManager
    from backend.models.task import Task
    from backend.orchestrator.processor import TaskProcessor
    from backend.routing.playbooks import PlaybookStore
    from backend.routing.tool_plan_types import ToolPlan, ToolPlanStep

    manager = ConfigManager(tmp_path)
    manager.init()
    config, _ = manager.load_merged()
    processor = TaskProcessor(config, data_dir=tmp_path)
    store = PlaybookStore(tmp_path)
    skill = store.get_by_name("html_slides")
    assert skill is not None
    task = Task(
        source="ui",
        user_id="admin",
        channel_id="c1",
        raw_text="slides",
        cleaned_intent="create slides",
    )
    plan = ToolPlan(
        goal="deck",
        confidence=0.97,
        tools_needed=["save_html_deck"],
        steps=[ToolPlanStep("save_html_deck", "save")],
        intent_class="html_slides",
        strategy="rules",
    )
    assert processor._execute_planned_direct(skill, task, None, plan) == (None, None)


def test_publish_continuation_plan_with_saved_deck():
    task = Task(
        source="ui",
        user_id="admin",
        channel_id="ui-1",
        raw_text="slug",
        cleaned_intent="yeah the slug `checkout-redirect-aug-2026` works",
    )
    plan = build_html_slides_tool_plan(
        task,
        skill_allowed=["save_html_deck", "publish_html_artifact"],
        session_metadata={
            "last_intent_class": "html_slides",
            "last_html_deck_filename": "presentation-1786635000.html",
            "pending_publish": True,
        },
    )
    assert plan is not None
    assert plan.tools_needed == ["publish_html_artifact"]
    assert plan.steps[0].args_hint.get("source_filename") == "presentation-1786635000.html"


def test_publish_plan_from_export_url_in_message():
    task = Task(
        source="ui",
        user_id="admin",
        channel_id="ui-1",
        raw_text="publish",
        cleaned_intent=(
            "yeah the slug `checkout-redirect-aug-2026` works can you publish "
            "/api/chat/exports/presentation-1786635000.html"
        ),
    )
    plan = build_html_slides_tool_plan(
        task,
        skill_allowed=["save_html_deck", "publish_html_artifact"],
        session_metadata={"last_intent_class": "html_slides", "pending_publish": True},
    )
    assert plan is not None
    assert plan.tools_needed == ["publish_html_artifact"]
    assert plan.steps[0].args_hint["slug"] == "checkout-redirect-aug-2026"
    assert plan.steps[0].args_hint["source_filename"] == "presentation-1786635000.html"


def test_publish_plan_without_slug_uses_sha_mode():
    task = Task(
        source="ui",
        user_id="admin",
        channel_id="ui-1",
        raw_text="publish",
        cleaned_intent="can you publish it and give me the link?",
    )
    plan = build_html_slides_tool_plan(
        task,
        skill_allowed=["save_html_deck", "publish_html_artifact"],
        session_metadata={
            "last_intent_class": "html_slides",
            "last_html_deck_filename": "presentation-1786635000.html",
        },
    )
    assert plan is not None
    assert plan.tools_needed == ["publish_html_artifact"]
    assert plan.steps[0].args_hint == {"source_filename": "presentation-1786635000.html"}
    assert "slug" not in plan.steps[0].args_hint


def test_publish_plan_routes_to_direct():
    from backend.orchestrator.graph.plan_routing import resolve_graph_route
    from backend.routing.tool_plan_types import ToolPlan, ToolPlanStep

    plan = ToolPlan(
        goal="Publish saved deck",
        confidence=0.98,
        tools_needed=["publish_html_artifact"],
        steps=[
            ToolPlanStep(
                "publish_html_artifact",
                "publish saved deck",
                {"source_filename": "presentation-1786635000.html"},
            )
        ],
        intent_class="html_slides",
        strategy="rules",
    )
    assert resolve_graph_route(plan, allowed_tools=["publish_html_artifact"]) == "direct"


def test_resolve_publish_html_args_fills_missing_slug_and_source(tmp_path):
    from backend.config_manager import ConfigManager
    from backend.paths import exports_dir
    from backend.tools.artifacts.register import register_artifact_tools
    from backend.tools.registry import ToolRegistry

    manager = ConfigManager(tmp_path)
    manager.init()
    config, _ = manager.load_merged()
    exports_dir(tmp_path).mkdir(parents=True, exist_ok=True)
    deck_path = exports_dir(tmp_path) / "presentation-1786635000.html"
    deck_path.write_text(SAMPLE, encoding="utf-8")

    task = Task(
        source="ui",
        user_id="admin",
        channel_id="ui-1",
        raw_text="publish",
        cleaned_intent="yeah the slug `checkout-redirect-aug-2026` works",
    )
    resolved = resolve_publish_html_args(
        {"html": SAMPLE},
        task=task,
        session_metadata={"last_html_deck_filename": "presentation-1786635000.html"},
    )
    assert resolved["slug"] == "checkout-redirect-aug-2026"
    assert "source_filename" not in resolved
    assert publish_args_complete(resolved)

    resolved_from_session = resolve_publish_html_args(
        {},
        task=task,
        session_metadata={"last_html_deck_filename": "presentation-1786635000.html"},
    )
    assert resolved_from_session["slug"] == "checkout-redirect-aug-2026"
    assert resolved_from_session["source_filename"] == "presentation-1786635000.html"

    registry = ToolRegistry()
    register_artifact_tools(registry, config=config, data_dir=tmp_path)
    registry.current_task = task
    registry.session_metadata = {"last_html_deck_filename": "presentation-1786635000.html"}
    result = registry.run(
        "publish_html_artifact",
        {"html": SAMPLE},
        allowed=["publish_html_artifact"],
    )
    assert result.kind == "html_artifact_published"
    assert result.data["slug"] == "checkout-redirect-aug-2026"


def test_extract_export_filename_from_text():
    assert (
        extract_export_filename_from_text("/api/chat/exports/presentation-1786635000.html")
        == "presentation-1786635000.html"
    )


def test_validate_tool_plan_keeps_publish_tool_for_html_slides(tmp_path):
    from backend.config_manager import ConfigManager
    from backend.routing.tool_plan_types import ToolPlan, ToolPlanStep
    from backend.routing.tool_plan_validator import validate_tool_plan
    from backend.tools.builder import build_git_tool_registry

    manager = ConfigManager(tmp_path)
    manager.init()
    config, _ = manager.load_merged()
    registry = build_git_tool_registry(config, data_dir=tmp_path, allowed_tools=["save_html_deck", "publish_html_artifact"])
    plan = ToolPlan(
        goal="save deck",
        confidence=0.97,
        tools_needed=["save_html_deck"],
        steps=[ToolPlanStep("save_html_deck", "save")],
        intent_class="html_slides",
        strategy="rules",
    )
    binding = validate_tool_plan(
        plan,
        registry,
        skill_allowed=["save_html_deck", "publish_html_artifact"],
        skill_name="html_slides",
    )
    assert "publish_html_artifact" in binding.allowed_tools
    assert "publish_html_artifact" in binding.manifest_text


def test_publish_from_source_filename(tmp_path):
    from backend.config_manager import ConfigManager
    from backend.paths import exports_dir
    from backend.tools.artifacts.register import register_artifact_tools
    from backend.tools.registry import ToolRegistry

    manager = ConfigManager(tmp_path)
    manager.init()
    config, _ = manager.load_merged()
    exports_dir(tmp_path).mkdir(parents=True, exist_ok=True)
    deck_path = exports_dir(tmp_path) / "presentation-1786635000.html"
    deck_path.write_text(SAMPLE, encoding="utf-8")

    registry = ToolRegistry()
    register_artifact_tools(registry, config=config, data_dir=tmp_path)
    result = registry.run(
        "publish_html_artifact",
        {
            "slug": "checkout-redirect-aug-2026",
            "source_filename": "presentation-1786635000.html",
            "title": "Checkout Redirect",
        },
        allowed=["publish_html_artifact"],
    )
    assert result.kind == "html_artifact_published"
    assert result.data["slug"] == "checkout-redirect-aug-2026"


def test_publish_without_slug_uses_sha_url(tmp_path):
    import hashlib

    from backend.config_manager import ConfigManager
    from backend.paths import exports_dir
    from backend.tools.artifacts.register import register_artifact_tools
    from backend.tools.registry import ToolRegistry

    manager = ConfigManager(tmp_path)
    manager.init()
    config, _ = manager.load_merged()
    exports_dir(tmp_path).mkdir(parents=True, exist_ok=True)
    deck_path = exports_dir(tmp_path) / "presentation-1786635000.html"
    deck_path.write_text(SAMPLE, encoding="utf-8")
    from backend.artifacts.html_deck import finalize_html_deck
    from backend.artifacts.slide_branding import build_slide_branding_context

    branding = build_slide_branding_context(config, tmp_path)
    expected_sha = hashlib.sha256(
        finalize_html_deck(deck_path.read_text(encoding="utf-8"), branding=branding).encode()
    ).hexdigest()

    registry = ToolRegistry()
    register_artifact_tools(registry, config=config, data_dir=tmp_path)
    result = registry.run(
        "publish_html_artifact",
        {"source_filename": "presentation-1786635000.html"},
        allowed=["publish_html_artifact"],
    )
    assert result.kind == "html_artifact_published"
    assert result.data["publish_mode"] == "sha"
    assert result.data["slug"] == ""
    assert result.data["sha256"] == expected_sha
    assert result.data["share_url"] == f"/artifacts/sha/{expected_sha}"


def test_creating_slides_matches_intent():
    assert looks_like_html_slides_request("can you try creating slides again")


def test_followup_with_session_context():
    from backend.models.session import ConversationSession, ConversationTurn

    session = ConversationSession(
        key="ui:x:x",
        source="ui",
        scope_id="x",
        thread_id="x",
        metadata={"last_intent_class": "html_slides"},
        turns=[
            ConversationTurn(role="user", content="create a presentation"),
            ConversationTurn(role="assistant", content="failed"),
        ],
    )
    task = Task(
        source="ui",
        user_id="admin",
        channel_id="ui-1",
        raw_text="try again",
        cleaned_intent="can you try again on checkout data",
    )
    assert looks_like_html_slides_followup(task, session)


def test_skill_policy_maps_html_slides_intent():
    from backend.orchestrator.graph.skill_policy import resolve_policy_skill
    from backend.routing.playbooks import PlaybookStore
    from backend.routing.tool_plan_types import ToolPlan, ToolPlanStep

    store = PlaybookStore(None)
    plan = ToolPlan(
        goal="slides",
        confidence=0.97,
        tools_needed=["save_html_deck"],
        steps=[ToolPlanStep("save_html_deck", "save")],
        intent_class="html_slides",
        strategy="rules",
    )
    skill = resolve_policy_skill(plan, store, fallback=None)
    assert skill is not None
    assert skill.name == "html_slides"


def test_build_html_slides_plan_for_artifact_only_skill():
    task = Task(
        source="ui",
        user_id="admin",
        channel_id="ui-1",
        raw_text="checkout redirect metrics table",
        cleaned_intent="here is the data — turn it into slides",
    )
    plan = build_html_slides_tool_plan(
        task,
        skill_allowed=["save_html_deck", "publish_html_artifact"],
    )
    assert plan is not None
    assert plan.intent_class == "html_slides"
    assert plan.tools_needed == ["save_html_deck"]


def test_build_html_slides_plan_with_slug_includes_publish():
    task = Task(
        source="ui",
        user_id="admin",
        channel_id="ui-1",
        raw_text="presentation",
        cleaned_intent=(
            "create a presentation from checkout redirect data use slug "
            "`checkout-redirect-aug-2026`"
        ),
    )
    plan = build_html_slides_tool_plan(
        task,
        skill_allowed=["save_html_deck", "publish_html_artifact"],
    )
    assert plan is not None
    assert plan.tools_needed == ["save_html_deck", "publish_html_artifact"]
    assert plan.steps[-1].args_hint.get("slug") == "checkout-redirect-aug-2026"


def test_resolve_tool_plan_prefers_html_slides_over_llm_path():
    config = AlfredConfig()
    config.routing.tool_planner_enabled = True
    config.routing.planner_strategy = "llm_first"
    task = Task(
        source="ui",
        user_id="admin",
        channel_id="ui-1",
        raw_text="presentation",
        cleaned_intent="create a presentation on checkout redirect success rates",
        metadata={"chat_persona_effective": "all"},
    )
    context = RouteContext(intent=task.cleaned_intent, mode=RouteMode.INVESTIGATION)
    plan = resolve_tool_plan(
        config,
        task,
        context,
        skill_allowed=["save_html_deck", "publish_html_artifact"],
    )
    assert plan is not None
    assert plan.intent_class == "html_slides"
    assert plan.strategy == "rules"


def test_html_slides_manifest_addendum():
    text = html_slides_tool_manifest_addendum()
    assert "save_html_deck" in text
    assert "succeeded" in text.lower()


def test_inject_html_slides_bootstrap_message():
    from backend.ai.base import Message

    task = Task(
        source="ui",
        user_id="admin",
        channel_id="ui-1",
        raw_text="slides",
        cleaned_intent="create a presentation",
    )
    messages = inject_html_slides_bootstrap_message(
        [Message(role="user", content="create a presentation")],
        task,
    )
    assert len(messages) == 2
    assert "save_html_deck" in messages[0].content


def test_plan_tools_rules_html_slides():
    task = Task(
        source="ui",
        user_id="admin",
        channel_id="ui-1",
        raw_text="create a presentation",
        cleaned_intent="create a presentation from checkout metrics",
    )
    plan = plan_tools_rules(
        task,
        entities=EntityBag(),
        skill_allowed=["save_html_deck", "publish_html_artifact"],
    )
    assert plan is not None
    assert plan.intent_class == "html_slides"
    assert "save_html_deck" in plan.tools_needed


def test_ui_support_persona_skips_doc_plan_for_presentation():
    config = AlfredConfig()
    config.routing.tool_planner_enabled = True
    task = Task(
        source="ui",
        user_id="admin",
        channel_id="ui-1",
        raw_text="create a presentation",
        cleaned_intent="create a presentation on checkout redirect success rates",
        metadata={"chat_persona_effective": "support"},
    )
    context = RouteContext(intent=task.cleaned_intent, mode=RouteMode.INVESTIGATION)
    plan = resolve_tool_plan(
        config,
        task,
        context,
        skill_allowed=["save_html_deck", "publish_html_artifact"],
    )
    assert plan is not None
    assert plan.intent_class == "html_slides"


def test_salvage_html_deck_from_inline_prose(tmp_path):
    manager = ConfigManager(tmp_path)
    manager.init()
    config, _ = manager.load_merged()
    registry = ToolRegistry()
    register_artifact_tools(registry, config=config, data_dir=tmp_path)

    prose = f"Here is your deck:\n\n```html\n{SAMPLE}\n```\n"
    result = salvage_html_deck_from_prose(
        prose,
        registry,
        allowed_tools=["save_html_deck"],
    )
    assert result is not None
    assert result.kind == "html_deck_saved"
    assert (tmp_path / "exports" / "checkout-redirect.html").is_file()


def test_html_slides_grounding_requires_artifact_tool():
    plan = ToolPlan(
        goal="Create deck",
        confidence=0.9,
        tools_needed=["save_html_deck"],
        steps=[ToolPlanStep("save_html_deck", "save")],
        intent_class="html_slides",
        strategy="rules",
    )
    goal = goal_spec_from_plan(plan)
    result = validate_agent_result(
        "I've created your presentation with all the metrics.",
        [],
        goal,
    )
    assert not result.passed
    assert "artifact tool" in result.issues[0].lower()


def test_html_slides_grounding_passes_after_save():
    plan = ToolPlan(
        goal="Create deck",
        confidence=0.9,
        tools_needed=["save_html_deck"],
        steps=[ToolPlanStep("save_html_deck", "save")],
        intent_class="html_slides",
        strategy="rules",
    )
    goal = goal_spec_from_plan(plan)
    trace = [
        ToolTraceEntry(
            tool="save_html_deck",
            success=True,
            result_kind="html_deck_saved",
            observation='{"kind":"html_deck_saved","data":{"download_url":"/api/chat/exports/deck.html"}}',
        )
    ]
    result = validate_agent_result(
        "Saved your deck — download at /api/chat/exports/deck.html",
        trace,
        goal,
    )
    assert result.passed


def test_html_slides_grounding_matches_absolute_publish_url():
    plan = ToolPlan(
        goal="Publish deck",
        confidence=0.9,
        tools_needed=["publish_html_artifact"],
        steps=[ToolPlanStep("publish_html_artifact", "publish")],
        intent_class="html_slides",
        strategy="rules",
    )
    goal = goal_spec_from_plan(plan)
    trace = [
        ToolTraceEntry(
            tool="publish_html_artifact",
            success=True,
            result_kind="html_artifact_published",
            observation=(
                '{"kind":"html_artifact_published","data":{'
                '"share_url":"/artifacts/s/checkout-redirect-aug-2026",'
                '"slug_url":"/artifacts/s/checkout-redirect-aug-2026"}}'
            ),
        )
    ]
    result = validate_agent_result(
        "Published: http://localhost:8080/artifacts/s/checkout-redirect-aug-2026",
        trace,
        goal,
    )
    assert result.passed


def test_html_slides_grounding_rejects_invented_share_url():
    plan = ToolPlan(
        goal="Create deck",
        confidence=0.9,
        tools_needed=["save_html_deck", "publish_html_artifact"],
        steps=[ToolPlanStep("save_html_deck", "save")],
        intent_class="html_slides",
        strategy="rules",
    )
    goal = goal_spec_from_plan(plan)
    result = validate_agent_result(
        "Done — view at http://localhost:8080/artifacts/s/checkout-redirect-aug-2026",
        [],
        goal,
    )
    assert not result.passed
    assert "save_html_deck" in result.issues[0].lower()
    assert "Issues:" in result.fallback


def test_html_slides_addendum_mentions_save_tool():
    task = Task(
        source="ui",
        user_id="admin",
        channel_id="ui-1",
        raw_text="slides",
        cleaned_intent="slides",
    )
    text = html_slides_system_addendum(task)
    assert "save_html_deck" in text
    assert "exports" in text
