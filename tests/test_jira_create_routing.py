"""Tests for JIRA create intent routing and channel project resolution."""

from __future__ import annotations

from backend.routing.jira_intent import (
    looks_like_jira_create_followup,
    looks_like_jira_create_request,
)
from backend.models.config import AlfredConfig, JiraConfig, SlackConfig, SlackListJiraSyncConfig
from backend.models.task import Task
from backend.routing.engine import SkillRouter
from backend.routing.jira_context import resolve_jira_project_for_task
from backend.routing.jira_direct import jira_create_route_decision, looks_like_jira_question
from backend.routing.playbooks import PlaybookStore
from backend.routing.types import RouteContext, RouteMode


def _task(*, raw: str, cleaned: str, channel_id: str = "C_TECH") -> Task:
    return Task(
        source="slack",
        user_id="UAMIT",
        channel_id=channel_id,
        thread_ts="1.0",
        raw_text=raw,
        cleaned_intent=cleaned,
    )


def test_create_above_ticket_matches_create_request():
    intent = "create the above ticket in TS board?"
    assert looks_like_jira_create_request(intent)
    assert looks_like_jira_question(intent)


def test_project_key_followup_without_ticket_word():
    intent = "i mentioned the project key is TS and remember #tech-support is always TS"
    session = (
        "create the above ticket in TS board",
        "Merchant QueensNdolls integration breaking",
    )
    assert looks_like_jira_create_followup(intent, session_turns=session)
    assert looks_like_jira_question(intent, session_turns=session)


def test_jira_create_route_decision_for_followup():
    config = AlfredConfig()
    config.jira = JiraConfig(enabled=True)
    store = PlaybookStore()
    context = RouteContext(
        intent="project key is TS — create it on the TS board",
        mode=RouteMode.INVESTIGATION,
        session_turns=(
            "create the above ticket",
            "Summary: Integration with delivery app breaking",
        ),
    )
    decision = jira_create_route_decision(context, store, config)
    assert decision.matched
    assert decision.skill_name == "jira_management"


def test_skill_router_prioritizes_jira_create():
    config = AlfredConfig()
    config.jira = JiraConfig(enabled=True, api_token="x", email="a@b.com", base_url="https://x.atlassian.net")
    store = PlaybookStore()
    router = SkillRouter(config, store)
    context = RouteContext(
        intent="remember project key TS for #tech-support",
        mode=RouteMode.INVESTIGATION,
        session_turns=("create ticket for merchant issue",),
        thread_context="Status: Not picked\nMerchant: ExampleCo",
    )
    result = router.route(context)
    assert result.playbook is not None
    assert result.playbook.name == "jira_management"


def test_resolve_jira_project_from_list_jira_sync_channel():
    config = AlfredConfig()
    config.slack = SlackConfig(
        enabled=True,
        list_jira_sync=SlackListJiraSyncConfig(
            enabled=True,
            jira_project="TS",
            channel_ids=["C_TECH"],
        ),
    )
    task = _task(raw="", cleaned="create ticket", channel_id="C_TECH")
    assert resolve_jira_project_for_task(task, config) == "TS"


def test_resolve_jira_project_from_channel_projects_map():
    config = AlfredConfig()
    config.jira = JiraConfig(enabled=True, channel_projects={"C_TECH": "TS"})
    task = _task(raw="", cleaned="create ticket", channel_id="C_TECH")
    assert resolve_jira_project_for_task(task, config) == "TS"
