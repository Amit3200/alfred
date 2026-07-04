"""Tests for investigation / git agent path in processor."""

from __future__ import annotations
from backend.integrations.git.api import PullRequestSummary
from backend.routing.playbooks import PlaybookStore


from pathlib import Path
from unittest.mock import MagicMock, patch

from backend.ai.base import LLMResponse
from backend.orchestrator.processor import TaskProcessor
from backend.formatting.render import render_for_channel
from backend.models.config import GitConfig, default_config
from backend.models.task import Task


def test_processor_runs_investigation_loop_for_pr_question():
    config = default_config()
    config.git = GitConfig(enabled=True, provider="github", token="ghp_test")

    processor = TaskProcessor(config)
    processor.router = MagicMock()

    with patch("backend.tools.git_api.GitApiClient") as mock_client_cls:
        pass

        mock_client = mock_client_cls.from_alfred_config.return_value
        mock_client.list_my_prs.return_value = [
            PullRequestSummary(
                number=7,
                title="Fix orders",
                state="open",
                repo="myorg/backend",
                author="alice",
                url="https://github.com/myorg/backend/pull/7",
            ),
        ]

        task = Task(
            source="cli",
            user_id="cli",
            raw_text="what are my open prs?",
            cleaned_intent="what are my open prs?",
        )
        response = processor.process(task)

    reply = render_for_channel(response, "cli")
    assert response.payload.kind == "pr_list"
    assert "#7" in reply


def test_bundled_git_status_skill_loads(tmp_path: Path):
    pass

    store = PlaybookStore(tmp_path)
    names = {p.name for p in store.list_playbooks()}
    assert "git_status" in names

    matched = store.pick_investigation("what are my open prs?")
    assert matched is not None
    assert matched.name == "git_status"
    assert "list_my_prs" in matched.allowed_tools


def test_investigation_skipped_when_git_disabled(tmp_path: Path):
    config = default_config()
    config.git.enabled = False

    mock_provider = MagicMock()
    mock_provider.chat.return_value = LLMResponse(content="plain answer", tool_calls=[])

    processor = TaskProcessor(config, data_dir=tmp_path)
    processor.router = MagicMock()
    processor.router.get.return_value = mock_provider

    task = Task(
        source="cli",
        user_id="cli",
        raw_text="my open prs",
        cleaned_intent="my open prs",
    )
    response = processor.process(task)

    assert response.payload.kind == "text"
    assert response.payload.data["text"] == "plain answer"
    assert mock_provider.chat.call_args.kwargs.get("tools") is None
