"""Tests for deterministic git investigation formatting in processor."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from backend.integrations.git.api import PullRequestSummary
from backend.orchestrator.processor import TaskProcessor
from backend.formatting.render import render_for_channel
from backend.models.config import GitConfig, default_config
from backend.models.task import Task
from backend.tools.registry import ToolRegistry
from backend.tools.result import ToolResult


def test_processor_uses_structured_pr_payload():
    config = default_config()
    config.git = GitConfig(enabled=True, provider="github", token="ghp_test")

    processor = TaskProcessor(config)
    processor.router = MagicMock()
    processor.router.get.return_value = MagicMock(is_available=lambda: True)

    prs = [
        PullRequestSummary(
            number=1685,
            title="Thanks page",
            state="open",
            repo="AcmeCorp/platform",
            author="alice",
            url="https://github.com/AcmeCorp/platform/pull/1685",
        ),
    ]

    registry = ToolRegistry()
    registry.last_result = ToolResult.pr_list(prs, state="open")

    with patch("backend.agent.loop.run_agent_loop", return_value=""):
        with patch.object(processor, "_try_unified_direct", return_value=(None, None)):
            with patch(
                "backend.tools.git_api.build_git_tool_registry",
                return_value=registry,
            ):
                task = Task(
                    source="slack",
                    user_id="U1",
                    channel_id="C1",
                    raw_text="@alfred my open prs",
                    cleaned_intent="my open prs",
                )
                response = processor.process(task)

    assert response.payload.kind == "pr_list"
    reply = render_for_channel(response, "slack")
    assert "*1 open PR*" in reply
    assert "<https://github.com/AcmeCorp/platform/pull/1685|#1685 Thanks page>" in reply
