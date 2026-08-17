"""Phase 1 tests — tool planner, entity extraction, scoped binding."""

from __future__ import annotations

from unittest.mock import MagicMock

from backend.models.config import AlfredConfig, RoutingConfig
from backend.models.task import Task
from backend.routing.entity_extractor import extract_entities
from backend.routing.tool_plan_types import ToolPlan
from backend.routing.tool_plan_validator import validate_tool_plan
from backend.routing.tool_planner import plan_tools_rules, resolve_tool_plan
from backend.routing.types import RouteContext
from backend.tools.catalog_formatter import format_tool_manifest
from backend.tools.registry import ToolRegistry


def _task(cleaned: str, raw: str = "") -> Task:
    return Task(
        source="slack",
        user_id="U1",
        channel_id="C1",
        thread_ts="1.0",
        raw_text=raw or cleaned,
        cleaned_intent=cleaned,
    )


def test_extract_entities_issue_key_and_sheet_url():
    entities = extract_entities(
        "check ENG-123 and https://docs.google.com/spreadsheets/d/abc123XYZ/edit"
    )
    assert "ENG-123" in entities.issue_keys
    assert "abc123XYZ" in entities.spreadsheet_ids


def test_plan_create_google_sheet():
    task = _task("can you create a google sheet from the csv above?")
    entities = extract_entities(task.cleaned_intent)
    plan = plan_tools_rules(
        task,
        entities,
        skill_allowed=[
            "google_create_sheet",
            "google_write_sheet",
            "google_read_sheet",
        ],
    )
    assert plan is not None
    assert plan.confidence >= 0.85
    assert "google_create_sheet" in plan.tools_needed
    assert plan.intent_class == "google.create.sheet"


def test_plan_assign_jira_issue():
    task = _task("assign ENG-99 to @Alice on jira", raw="assign ENG-99 to Alice")
    entities = extract_entities(task.cleaned_intent, task.raw_text)
    plan = plan_tools_rules(
        task,
        entities,
        skill_allowed=["jira_assign_issue", "get_jira_issue"],
    )
    assert plan is not None
    assert plan.tools_needed == ["jira_assign_issue"]


def test_validate_tool_plan_rejects_unknown_tools():
    registry = ToolRegistry()
    plan = ToolPlan(
        goal="test",
        confidence=0.9,
        tools_needed=["google_create_sheet", "nonexistent_tool"],
        missing_capabilities=["nonexistent_tool"],
    )
    binding = validate_tool_plan(
        plan,
        registry,
        skill_allowed=["google_create_sheet"],
        skill_name="google_workspace",
    )
    assert "google_create_sheet" not in binding.allowed_tools
    assert "Tool manifest" in binding.manifest_text


def test_format_tool_manifest_lists_allowed_only():
    text = format_tool_manifest(["google_create_sheet", "google_write_sheet"])
    assert "google_create_sheet" in text
    assert "EXACTLY" in text


def test_resolve_tool_plan_rules_without_llm():
    config = AlfredConfig(
        routing=RoutingConfig(
            tool_planner_llm_fallback=False,
            planner_strategy="rules_first",
        )
    )
    task = _task("create a google sheet titled Redirect Report")
    ctx = RouteContext(intent=task.cleaned_intent, channel_id="C1")
    plan = resolve_tool_plan(
        config,
        task,
        ctx,
        provider=None,
        skill_allowed=["google_create_sheet", "google_write_sheet"],
    )
    assert plan is not None
    assert "google_create_sheet" in plan.tools_needed


def test_resolve_tool_plan_disabled():
    config = AlfredConfig(routing=RoutingConfig(tool_planner_enabled=False))
    task = _task("create google sheet")
    ctx = RouteContext(intent=task.cleaned_intent)
    assert resolve_tool_plan(config, task, ctx) is None
