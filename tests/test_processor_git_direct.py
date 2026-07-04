"""Tests for direct git tool path in processor."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from backend.integrations.git.api import PullRequestSummary
from backend.orchestrator.processor import TaskProcessor
from backend.formatting.render import render_for_channel
from backend.models.config import GitConfig, default_config
from backend.models.task import Task


def test_processor_direct_list_my_prs_skips_llm():
    config = default_config()
    config.git = GitConfig(enabled=True, provider="github", token="ghp_test")

    processor = TaskProcessor(config)
    processor.router = MagicMock()

    prs = [
        PullRequestSummary(
            number=7,
            title="Fix",
            state="open",
            repo="org/repo",
            author="alice",
            url="https://github.com/org/repo/pull/7",
        ),
    ]

    with patch("backend.tools.git_api.GitApiClient") as mock_client_cls:
        mock_client = mock_client_cls.from_alfred_config.return_value
        mock_client.list_my_prs.return_value = prs

        with patch("backend.agent.loop.run_agent_loop") as mock_loop:
            task = Task(
                source="slack",
                user_id="U1",
                channel_id="C1",
                raw_text="@alfred what are open PRs of mine?",
                cleaned_intent="what are open PRs of mine?",
            )
            response = processor.process(task)

    reply = render_for_channel(response, "slack")
    assert response.payload.kind == "pr_list"
    assert "*1 open PR*" in reply
    assert "#7 Fix" in reply
    mock_loop.assert_not_called()
