"""Tests for the skill routing SDK."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from backend.routing.playbooks import PlaybookStore
from backend.models.config import AlfredConfig, SkillsConfig, default_config
from backend.routing import RouteContext, RouteMode, SkillRouter
from backend.routing.heuristics import route_by_heuristic
from backend.routing.keyword import route_by_keyword
from backend.routing.llm import LLMSkillMatcher, parse_router_json


def test_parse_router_json_from_fenced_block():
    text = 'Here you go:\n```json\n{"skill": "google_workspace", "confidence": 0.9, "reason": "doc"}\n```'
    parsed = parse_router_json(text)
    assert parsed is not None
    assert parsed["skill"] == "google_workspace"


def test_keyword_router_picks_longest_trigger(tmp_path: Path):
    playbooks = tmp_path / "playbooks"
    playbooks.mkdir()
    (playbooks / "a.md").write_text(
        """---
name: skill_a
mode: investigation
triggers: [webhook]
allowed_tools: [grep]
---
body
""",
        encoding="utf-8",
    )
    (playbooks / "b.md").write_text(
        """---
name: skill_b
mode: investigation
triggers: [payment webhook]
allowed_tools: [grep]
---
body
""",
        encoding="utf-8",
    )
    store = PlaybookStore(tmp_path)
    ctx = RouteContext(intent="payment webhook failing", mode=RouteMode.INVESTIGATION)
    decision = route_by_keyword(ctx, store)
    assert decision.strategy == "keyword"
    assert decision.skill_name == "skill_b"


def test_heuristic_routes_code_investigation(tmp_path: Path):
    store = PlaybookStore(tmp_path)
    config = default_config()
    config.git.enabled = True
    ctx = RouteContext(
        intent="where is recalculateSession handled?",
        mode=RouteMode.INVESTIGATION,
    )
    decision = route_by_heuristic(ctx, store, config)
    assert decision.skill_name == "investigate_bug"
    assert decision.strategy == "heuristic"


def test_llm_router_picks_google_workspace(tmp_path: Path):
    store = PlaybookStore(tmp_path)
    provider = MagicMock()
    provider.is_available.return_value = True
    provider.chat.return_value = MagicMock(
        content='{"skill": "google_workspace", "confidence": 0.92, "reason": "create a doc"}'
    )
    matcher = LLMSkillMatcher(provider, model="test-model")
    ctx = RouteContext(
        intent="can you dump all this in a doc?",
        mode=RouteMode.INVESTIGATION,
        thread_context="Summary of merchant traffic data…",
    )
    decision = matcher.match(ctx, store)
    assert decision.strategy == "llm"
    assert decision.skill_name == "google_workspace"
    assert decision.confidence >= 0.55


def test_llm_router_rejects_low_confidence(tmp_path: Path):
    store = PlaybookStore(tmp_path)
    provider = MagicMock()
    provider.chat.return_value = MagicMock(
        content='{"skill": "google_workspace", "confidence": 0.2, "reason": "maybe"}'
    )
    matcher = LLMSkillMatcher(provider)
    ctx = RouteContext(intent="hello", mode=RouteMode.INVESTIGATION)
    decision = matcher.match(ctx, store)
    assert decision.skill_name is None


def test_hybrid_keyword_wins_over_llm(tmp_path: Path):
    playbooks = tmp_path / "playbooks"
    playbooks.mkdir()
    (playbooks / "google.md").write_text(
        """---
name: google_workspace
mode: investigation
triggers: [google doc]
allowed_tools: [google_create_doc]
---
body
""",
        encoding="utf-8",
    )
    store = PlaybookStore(tmp_path)
    provider = MagicMock()
    provider.is_available.return_value = True
    provider.chat.return_value = MagicMock(
        content='{"skill": "investigate_bug", "confidence": 0.99, "reason": "wrong"}'
    )
    llm_router = MagicMock()
    llm_router.resolve_task.return_value = ("kimi", provider, "m")

    config = default_config()
    router = SkillRouter(config, store, llm_router=llm_router)
    result = router.route_investigation(
        RouteContext(intent="put this in a google doc", mode=RouteMode.INVESTIGATION)
    )
    assert result.decision.strategy == "keyword"
    assert result.playbook is not None
    assert result.playbook.name == "google_workspace"
    provider.chat.assert_not_called()


def test_hybrid_llm_fallback_when_keywords_miss(tmp_path: Path):
    store = PlaybookStore(tmp_path)
    provider = MagicMock()
    provider.is_available.return_value = True
    provider.chat.return_value = MagicMock(
        content='{"skill": "google_workspace", "confidence": 0.88, "reason": "doc request"}'
    )
    llm_router = MagicMock()
    llm_router.resolve_task.return_value = ("kimi", provider, "m")

    config = default_config()
    router = SkillRouter(config, store, llm_router=llm_router)
    result = router.route_investigation(
        RouteContext(
            intent="dump this into a document please",
            mode=RouteMode.INVESTIGATION,
            thread_context="merchant metrics summary",
        )
    )
    assert result.decision.strategy == "llm"
    assert result.playbook is not None
    assert result.playbook.name == "google_workspace"


def test_agentic_routing_can_be_disabled(tmp_path: Path):
    store = PlaybookStore(tmp_path)
    provider = MagicMock()
    provider.is_available.return_value = True
    llm_router = MagicMock()
    llm_router.resolve_task.return_value = ("kimi", provider, "m")

    config = AlfredConfig(skills=SkillsConfig(agentic_routing=False))
    router = SkillRouter(config, store, llm_router=llm_router)
    result = router.route_investigation(
        RouteContext(intent="dump into a document", mode=RouteMode.INVESTIGATION)
    )
    assert result.playbook is None
    provider.chat.assert_not_called()
