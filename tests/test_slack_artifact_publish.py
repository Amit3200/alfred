"""Tests for Slack artifact publish tracking and formatting."""

from __future__ import annotations

from backend.artifacts.actor import resolve_publish_actor, slack_actor
from backend.artifacts.formatting import format_published_artifact_slack
from backend.config_manager import ConfigManager
from backend.models.task import Task
from backend.tools.artifacts_tool import register_artifact_tools
from backend.tools.registry import ToolRegistry

from tests.slide_fixtures import MINIMAL_SLIDE_HTML

SAMPLE = MINIMAL_SLIDE_HTML


def test_resolve_publish_actor_from_slack_task():
    task = Task(
        source="slack",
        user_id="U012ABC",
        channel_id="C1",
        raw_text="publish",
        cleaned_intent="publish slides",
        metadata={"slack_user_names": {"U012ABC": "Amit"}},
    )
    actor, source, slack_uid = resolve_publish_actor(task=task)
    assert actor.key == "slack:U012ABC"
    assert actor.label == "Amit"
    assert source == "slack"
    assert slack_uid == "U012ABC"


def test_publish_html_artifact_slack_actor_and_source(tmp_path):
    manager = ConfigManager(tmp_path)
    manager.init()
    config, _ = manager.load_merged()
    config.artifacts.public_base_url = "https://alfred.example.com"
    manager.save_merged(config, _)

    registry = ToolRegistry()
    registry.current_task = Task(
        source="slack",
        user_id="U99",
        channel_id="C1",
        raw_text="x",
        cleaned_intent="publish deck as team-review",
        metadata={"slack_user_names": {"U99": "Om Sinkar"}},
    )
    registry.alfred_config = config
    register_artifact_tools(registry, config=config, data_dir=tmp_path)

    result = registry.run(
        "publish_html_artifact",
        {"html": SAMPLE, "slug": "team-review", "title": "Team Review"},
        allowed=["publish_html_artifact"],
    )
    assert result.kind == "html_artifact_published"
    assert result.data["owner_key"] == "slack:U99"
    assert result.data["uploaded_by"] == "Om Sinkar"
    assert result.data["source"] == "slack"
    assert result.data["slack_user_id"] == "U99"
    assert result.data["share_url"] == "https://alfred.example.com/artifacts/s/team-review"

    from backend.db.artifacts_db import list_mine
    from backend.paths import db_path

    rows = list_mine(db_path(tmp_path), owner_key="slack:U99")
    assert len(rows) == 1
    assert rows[0]["slug"] == "team-review"


def test_format_published_artifact_slack_sha_mode():
    text = format_published_artifact_slack(
        {
            "sha256": "abc123" * 8 + "abcd",
            "publish_mode": "sha",
            "share_url": "https://alfred.example.com/artifacts/sha/abc123",
            "uploaded_by": "Admin",
            "source": "ui",
        }
    )
    assert "immutable" in text.lower()
    assert "https://alfred.example.com/artifacts/sha/abc123" in text


def test_format_published_artifact_slack_message():
    text = format_published_artifact_slack(
        {
            "slug": "team-review",
            "title": "Team Review",
            "share_url": "https://alfred.example.com/artifacts/s/team-review",
            "uploaded_by": "Om Sinkar",
            "source": "slack",
        }
    )
    assert "Published HTML slides" in text
    assert "https://alfred.example.com/artifacts/s/team-review" in text
    assert "via Slack" in text


def test_tool_result_published_artifact_uses_share_url_from_data():
    from backend.orchestrator.processor import _tool_result_to_response
    from backend.tools.result import ToolResult

    response = _tool_result_to_response(
        ToolResult(
            kind="html_artifact_published",
            data={
                "slug": "team-review",
                "title": "Team Review",
                "share_url": "https://alfred.example.com/artifacts/s/team-review",
                "uploaded_by": "Om Sinkar",
                "source": "slack",
            },
        ),
    )
    assert response is not None
    text = response.payload.data["text"]
    assert "https://alfred.example.com/artifacts/s/team-review" in text
    assert "via Slack" in text


def test_slack_actor_helper():
    actor = slack_actor("U1", "Test User")
    assert actor.key == "slack:U1"
    assert actor.label == "Test User"
