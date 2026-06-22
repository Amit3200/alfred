"""Tests for grade_events tool registration."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from backend.models.config import AWSConfig, AlfredConfig
from backend.tools.git_api import build_git_tool_registry
from backend.tools.result import ToolResult


def _config() -> AlfredConfig:
    config = AlfredConfig()
    config.aws = AWSConfig(
        enabled=True,
        allowed_services=["athena"],
        athena_database="analytics",
        athena_output_location="s3://bucket/athena/",
        grade_events_table="grade_events",
    )
    return config


@patch("backend.aws.grade_events.GradeEventsClient")
def test_grade_events_query_tool(mock_client_cls):
    client = MagicMock()
    mock_client_cls.from_config.return_value = client
    client.query.return_value = {
        "table": "grade_events",
        "row_count": 1,
        "columns": ["kind"],
        "rows": [{"kind": "page_view"}],
        "guardrails": {"limit": 200, "time_window": "last_2_hours"},
    }

    registry = build_git_tool_registry(_config())
    result = registry.run(
        "grade_events_query",
        {"session_id": "abc"},
        allowed=["grade_events_query"],
    )

    assert result.kind == "grade_events_query"
    client.query.assert_called_once()


def test_grade_events_playbook_is_routable(tmp_path):
    from backend.ingress.playbooks import PlaybookStore

    playbooks = tmp_path / "playbooks"
    playbooks.mkdir()
    (playbooks / "grade-events.md").write_text(
        """---
name: grade_events
mode: investigation
triggers:
  - check grade events
allowed_tools:
  - grade_events_query
---

Use grade_events_query.
""",
        encoding="utf-8",
    )
    store = PlaybookStore(tmp_path)
    skill = store.pick_investigation("can you check grade events for this session?")
    assert skill is not None
    assert skill.name == "grade_events"
    assert "grade_events_query" in skill.allowed_tools
