"""Tests for PR review routing and skill-guided investigation."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from backend.routing.git_direct import wants_pr_code_analysis
from backend.orchestrator.processor import TaskProcessor
from backend.models.config import GitConfig, default_config
from backend.models.task import Task


def test_wants_pr_code_analysis_with_review_and_url():
    intent = (
        "summarize and review PR "
        "https://github.com/AcmeCorp/adhocs/pull/91"
    )
    assert wants_pr_code_analysis(intent)


def test_wants_pr_code_analysis_false_for_list_prs():
    assert not wants_pr_code_analysis("what are my open prs?")


def test_processor_pr_review_uses_investigation_loop():
    config = default_config()
    config.git = GitConfig(enabled=True, provider="github", token="ghp_test")

    processor = TaskProcessor(config)
    processor.router = MagicMock()
    mock_provider = MagicMock()
    processor.router.get.return_value = mock_provider
    cfg = config.ai.providers[config.ai.routing.investigation.provider]
    cfg.enabled = True

    task = Task(
        source="ui",
        user_id="u1",
        channel_id="ui:abc:abc",
        raw_text="review this PR https://github.com/AcmeCorp/adhocs/pull/91",
        cleaned_intent="review this PR https://github.com/AcmeCorp/adhocs/pull/91",
    )

    with patch.object(
        processor,
        "_prefetch_pr_context",
        return_value=("## Pre-fetched PR data\nPR #91", {"repo": "AcmeCorp/adhocs", "number": 91}),
    ):
        with patch("backend.agent.loop.run_agent_loop", return_value="## 1. Executive Summary\nSafe.") as mock_loop:
            response = processor.process(task)

    assert "Executive Summary" in response.payload.data["text"]
    mock_loop.assert_called_once()


def test_processor_metadata_summary_when_no_review_keyword():
    config = default_config()
    config.git = GitConfig(enabled=True, provider="github", token="ghp_test")

    processor = TaskProcessor(config)
    processor.router = MagicMock()
    mock_provider = MagicMock()
    mock_provider.chat.return_value = MagicMock(content="Short summary from description.")
    processor.router.get.return_value = mock_provider
    processor.router.from_config = MagicMock(return_value=processor.router)

    task = Task(
        source="ui",
        user_id="u1",
        channel_id="ui:abc:abc",
        raw_text="summarize https://github.com/AcmeCorp/adhocs/pull/91",
        cleaned_intent="summarize https://github.com/AcmeCorp/adhocs/pull/91",
    )

    pr_detail = {
        "number": 91,
        "title": "SQS Consumer",
        "repo": "AcmeCorp/adhocs",
        "url": "https://github.com/AcmeCorp/adhocs/pull/91",
        "body": "Adds consumer",
        "head": "feature/sqs",
        "base": "main",
    }

    with patch("backend.tools.git_api.GitApiClient") as mock_client_cls:
        mock_client = mock_client_cls.from_alfred_config.return_value
        mock_client.get_pr.return_value = pr_detail
        with patch("backend.agent.loop.run_agent_loop") as mock_loop:
            with patch.object(processor, "_summarize_pr", return_value="Short summary from description."):
                response = processor.process(task)

    mock_loop.assert_not_called()
    assert "Short summary" in response.payload.data["text"]
