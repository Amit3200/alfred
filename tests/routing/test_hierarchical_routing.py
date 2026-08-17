"""Hierarchical prompt routing — parent then function/capability."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from backend.models.config import AlfredConfig, JiraConfig, SlackConfig
from backend.models.task import Task
from backend.routing.capabilities import capability_for_tool
from backend.routing.classifier.classify import IntentClassification, classify_intent
from backend.routing.classifier.hierarchical import classify_intent_hierarchical
from backend.routing.classifier.parents import enabled_parents
from backend.routing.classifier.query_context import QueryMetadata, gather_query_metadata
from backend.routing.resolver import resolve_turn


def _task(text: str) -> Task:
    return Task(
        source="slack",
        user_id="U1",
        channel_id="C1",
        thread_ts="1.0",
        raw_text=text,
        cleaned_intent=text,
    )


def _config() -> AlfredConfig:
    config = AlfredConfig()
    config.jira = JiraConfig(enabled=True, default_project="TECH")
    config.slack = SlackConfig(enabled=True, bot_token="xoxb-test")
    config.git.enabled = True
    return config


def _linked_meta(text: str = "create a task") -> QueryMetadata:
    return QueryMetadata(
        source="slack",
        channel_id="C1",
        thread_ts="1.0",
        user_id="U1",
        slack_board_linked=True,
        slack_board_name="Bugs",
        slack_board_list_id="F123",
        jira_enabled=True,
        jira_default_project="TECH",
        last_intent_class="",
        last_target_system="",
        ticket_create_target="",
        entities={},
    )


def test_enabled_parents_omit_jira_when_disabled():
    config = _config()
    config.jira.enabled = False
    names = {p.id for p in enabled_parents(config, slack_board_linked=True)}
    assert "jira" not in names
    assert "slack_board" in names
    assert "conversational" in names


def test_enabled_parents_omit_slack_board_when_channel_not_linked():
    names = {p.id for p in enabled_parents(_config(), slack_board_linked=False)}
    assert "slack_board" not in names
    assert "jira" in names


def test_query_metadata_prompt_includes_channel():
    meta = gather_query_metadata(_task("hi"), config=_config())
    block = meta.prompt_block()
    assert "channel_id: C1" in block
    assert "source: slack" in block


def test_capability_for_tool_prefers_fine_grained_bundle():
    assert capability_for_tool("jira_create_issue") == "jira.write.create"
    assert capability_for_tool("slack_board_create_task") == "slack.board.write.create"


def test_hierarchical_two_stage_selects_jira_create():
    provider = MagicMock()
    provider.is_available.return_value = True
    parent_resp = MagicMock(content='{"parent":"jira","confidence":0.95,"reason":"named JIRA"}')
    cap_resp = MagicMock(
        content='{"intent_class":"jira.write.create","confidence":0.93,"reason":"create ticket"}'
    )
    provider.chat.side_effect = [parent_resp, cap_resp]
    meta = gather_query_metadata(_task("create a TECH task in JIRA"), config=_config())
    with patch("backend.ai.registry.LLMRouter.from_config") as mock_router:
        mock_router.return_value.for_task.return_value = provider
        result = classify_intent_hierarchical(
            _task("create a TECH task in JIRA"),
            config=_config(),
            metadata=meta,
        )
    assert result is not None
    assert result.intent_class == "jira.write.create"
    assert result.target_system == "jira"
    assert result.strategy == "llm_hierarchical"
    assert provider.chat.call_count == 2
    parent_prompt = provider.chat.call_args_list[0].args[0][0].content
    function_prompt = provider.chat.call_args_list[1].args[0][0].content
    assert "`jira`:" in parent_prompt
    assert "Query metadata" in parent_prompt
    assert "jira_create_issue" in function_prompt
    assert "Functions of `jira`" in function_prompt


def test_hierarchical_maps_function_name_to_capability():
    provider = MagicMock()
    provider.is_available.return_value = True
    parent_resp = MagicMock(content='{"parent":"jira","confidence":0.9,"reason":"jira"}')
    cap_resp = MagicMock(content='{"tool":"jira_assign_issue","confidence":0.88,"reason":"assign"}')
    provider.chat.side_effect = [parent_resp, cap_resp]
    with patch("backend.ai.registry.LLMRouter.from_config") as mock_router:
        mock_router.return_value.for_task.return_value = provider
        result = classify_intent_hierarchical(
            _task("assign TECH-9 to me"),
            config=_config(),
            metadata=_linked_meta(),
        )
    assert result is not None
    assert result.intent_class == "jira.write.assign"


def test_hierarchical_ambiguous_create_is_conversational():
    provider = MagicMock()
    provider.is_available.return_value = True
    parent_resp = MagicMock(
        content=(
            '{"parent":"conversational","confidence":0.7,'
            '"reason":"jira vs board","ambiguous_with":["jira","slack_board"]}'
        )
    )
    provider.chat.return_value = parent_resp
    with patch("backend.ai.registry.LLMRouter.from_config") as mock_router:
        mock_router.return_value.for_task.return_value = provider
        result = classify_intent_hierarchical(
            _task("create a task for coupon freebie"),
            config=_config(),
            metadata=_linked_meta(),
        )
    assert result is not None
    assert result.intent_class == "conversational"
    assert result.ambiguous_with == ("jira.write.create", "slack.board.write.create")
    assert provider.chat.call_count == 1


def test_hierarchical_unavailable_provider_returns_none():
    provider = MagicMock()
    provider.is_available.return_value = False
    meta = gather_query_metadata(_task("create a task"), config=_config())
    with patch("backend.ai.registry.LLMRouter.from_config") as mock_router:
        mock_router.return_value.for_task.return_value = provider
        result = classify_intent_hierarchical(_task("create a task"), config=_config(), metadata=meta)
    assert result is None


def test_resolve_turn_falls_back_to_rules_when_llm_unavailable():
    config = _config()
    config.routing.classifier_enabled = True
    with patch(
        "backend.routing.classifier.hierarchical.classify_intent_hierarchical",
        return_value=None,
    ):
        plan = resolve_turn(_task("create a task to add freebie in JIRA on TECH board"), config=config)
    assert plan.intent_class == "jira.write.create"
    assert plan.prefers_jira


def test_entity_direct_issue_key_skips_llm():
    config = _config()
    config.routing.classifier_enabled = True
    with patch(
        "backend.routing.classifier.hierarchical.classify_intent_hierarchical"
    ) as mock_llm:
        plan = resolve_turn(_task("TECH-12"), config=config)
    mock_llm.assert_not_called()
    assert plan.intent_class == "jira.read.single"
    assert plan.route == "direct"
    assert plan.strategy == "entity_direct"


def test_classify_intent_uses_hierarchical_when_enabled():
    config = _config()
    config.routing.classifier_enabled = True
    fake = IntentClassification(
        intent_class="web.search",
        target_system="web",
        confidence=0.91,
        strategy="llm_hierarchical",
    )
    with patch(
        "backend.routing.classifier.hierarchical.classify_intent_hierarchical",
        return_value=fake,
    ):
        result = classify_intent(_task("search the public docs for httponly cookies"), config=config)
    assert result.intent_class == "web.search"
    assert result.strategy == "llm_hierarchical"


def test_conversational_turn_plan_does_not_open_tools():
    config = _config()
    config.routing.classifier_enabled = True
    fake = IntentClassification(
        intent_class="conversational",
        target_system="",
        confidence=0.8,
        ambiguous_with=("jira.write.create", "slack.board.write.create"),
        strategy="llm_hierarchical",
    )
    with patch(
        "backend.routing.classifier.hierarchical.classify_intent_hierarchical",
        return_value=fake,
    ):
        plan = resolve_turn(_task("create a task for coupon freebie"), config=config)
    assert plan.route == "conversational"
    assert plan.intent_class == "conversational"
