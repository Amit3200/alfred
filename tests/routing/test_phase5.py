"""Phase 5 — class-based tools, domain services, and turn resolver."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from backend.models.config import AlfredConfig, JiraConfig
from backend.models.task import Task
from backend.routing.capabilities import bundle_tools, tools_for_capability
from backend.routing.classifier.intent_classes import (
    canonical_intent_class,
    is_html_slides_intent,
    is_slack_board_create_intent,
    legacy_intent_class,
)
from backend.routing.playbooks import _parse_playbook_index
from backend.routing.policies import resolve_playbook_allowed_tools
from backend.routing.resolver import resolve_turn
from backend.tools.base.tool import ToolContext
from backend.tools.catalog_formatter import get_tool_description
from backend.tools.jira.write import JiraCreateIssueTool
from backend.tools.registry import ToolRegistry
from backend.tools.result import ToolResult
from backend.tools.slack.board_tools import SlackBoardCreateTaskTool


def _config(*, jira: bool = True) -> AlfredConfig:
    config = AlfredConfig()
    config.jira = JiraConfig(
        enabled=jira,
        base_url="https://example.atlassian.net",
        email="dev@example.com",
        api_token="secret",
        default_project="TECH",
    )
    # Deterministic rules contract; hierarchical LLM path is tested separately.
    config.routing.classifier_enabled = False
    return config


def _task(text: str, *, source: str = "slack") -> Task:
    return Task(
        source=source,  # type: ignore[arg-type]
        user_id="U1",
        channel_id="C1",
        thread_ts="1.0",
        raw_text=text,
        cleaned_intent=text,
    )


def test_canonical_intent_aliases():
    assert canonical_intent_class("slack.board.create") == "slack.board.write.create"
    assert canonical_intent_class("html_slides") == "artifact.write.deck"
    assert legacy_intent_class("slack.board.write.create") == "slack.board.create"
    assert legacy_intent_class("artifact.write.deck") == "html_slides"
    assert is_html_slides_intent("html_slides")
    assert is_slack_board_create_intent("slack.board.create")


def test_resolve_turn_explicit_jira_create():
    intent = "create a task to add freebie using coupon in JIRA on TECH board"
    plan = resolve_turn(_task(intent), config=_config())
    assert plan.intent_class == "jira.write.create"
    assert plan.capability == "jira.write.create"
    assert plan.prefers_jira
    assert not plan.prefers_slack_board
    assert plan.tools == ["jira_create_issue"]
    assert plan.skill_name == "jira_management"


def test_resolve_turn_slack_board_create_without_jira_markers():
    intent = "create a task for payment delay on the board"
    plan = resolve_turn(_task(intent), config=_config())
    assert plan.intent_class == "slack.board.write.create"
    assert plan.prefers_slack_board
    assert not plan.prefers_jira
    assert "slack_board_create_task" in plan.tools


def test_resolve_turn_jira_followup_after_thread_context():
    session = SimpleNamespace(
        metadata={},
        turns=[
            SimpleNamespace(content="Governance: jira_create_issue requires explicit approval"),
            SimpleNamespace(content="create this on JIRA dashboard with TECH board"),
        ],
    )
    plan = resolve_turn(_task("yup go ahead and create"), config=_config(), session=session)
    assert plan.prefers_jira
    assert plan.intent_class == "jira.write.create"


def test_resolve_turn_ticket_create_target_metadata():
    session = SimpleNamespace(metadata={"ticket_create_target": "jira"}, turns=[])
    plan = resolve_turn(_task("create a task for coupon freebie"), config=_config(), session=session)
    assert plan.prefers_jira
    assert plan.intent_class == "jira.write.create"


def test_capability_bundle_jira_write_create():
    assert bundle_tools("jira.write.create") == ["jira_create_issue"]
    assert tools_for_capability("jira.write.create") == ["jira_create_issue"]


def test_jira_create_issue_tool_class_uses_domain_service():
    client_result = {
        "key": "TECH-9",
        "url": "https://example.atlassian.net/browse/TECH-9",
        "summary": "Coupon freebie",
        "issue_type": "Task",
        "project": "TECH",
    }
    ctx = ToolContext(config=_config(), channel_id="C123", thread_ts="111.222")
    with patch("backend.tools.jira.write.JiraService.from_config") as mock_svc:
        mock_svc.return_value.create_issue.return_value = client_result
        result = JiraCreateIssueTool().run(
            ctx,
            {"summary": "Coupon freebie", "description": "Show why COD is disabled."},
        )
    assert result.kind == "jira_action"
    req = mock_svc.return_value.create_issue.call_args[0][0]
    assert "Show why COD is disabled." in req.description
    assert "Slack thread:" in req.description
    assert "C123" in req.description


def test_jira_create_issue_tool_validates_missing_summary():
    ctx = ToolContext(config=_config())
    result = JiraCreateIssueTool().run(ctx, {"project": "TECH", "issue_type": "Task"})
    assert result.kind == "error"


def test_slack_board_create_tool_requires_title():
    ctx = ToolContext(config=_config(jira=False), channel_id="C1")
    result = SlackBoardCreateTaskTool().run(ctx, {})
    assert result.kind == "error"
    assert "title" in str(result.data.get("message") or "").lower()


def test_register_tool_binds_base_tool():
    registry = ToolRegistry()
    registry.alfred_config = _config()  # type: ignore[attr-defined]
    tool = JiraCreateIssueTool()
    registry.register_tool(tool)
    assert "jira_create_issue" in registry._tools
    with patch("backend.tools.jira.write.JiraService.from_config") as mock_svc:
        mock_svc.return_value.create_issue.return_value = {
            "key": "TECH-1",
            "url": "https://example.atlassian.net/browse/TECH-1",
        }
        result = registry.run(
            "jira_create_issue",
            {"project": "TECH", "summary": "X", "issue_type": "Task"},
            allowed=["jira_create_issue"],
        )
    assert isinstance(result, ToolResult)
    assert result.kind == "jira_action"


def test_catalog_description_comes_from_class_tool():
    desc = get_tool_description("jira_create_issue")
    assert "jira" in desc.lower() or "issue" in desc.lower()


def test_playbook_allowed_capabilities(tmp_path):
    path = tmp_path / "cap_skill.md"
    path.write_text(
        """---
name: cap_skill
mode: investigation
allowed_capabilities:
  - jira.write.create
---
# body
""",
        encoding="utf-8",
    )
    playbook = _parse_playbook_index(path, bundled=False)
    assert playbook.allowed_capabilities == ["jira.write.create"]
    assert resolve_playbook_allowed_tools(playbook) == ["jira_create_issue"]
