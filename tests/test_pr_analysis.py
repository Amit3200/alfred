"""Tests for PR code analysis routing and orchestration."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from backend.ingress.git_direct import wants_pr_code_analysis
from backend.ingress.processor import TaskProcessor
from backend.models.config import GitConfig, default_config
from backend.models.task import Task


def test_wants_pr_code_analysis_with_review_and_url():
    intent = (
        "summarize and review PR "
        "https://github.com/FlexyPe/flexype-adhocs/pull/91"
    )
    assert wants_pr_code_analysis(intent)


def test_wants_pr_code_analysis_false_for_list_prs():
    assert not wants_pr_code_analysis("what are my open prs?")


def test_processor_direct_pr_analysis_skips_llm_agent():
    config = default_config()
    config.git = GitConfig(enabled=True, provider="github", token="ghp_test")

    processor = TaskProcessor(config)
    processor.router = MagicMock()

    task = Task(
        source="ui",
        user_id="u1",
        channel_id="ui:abc:abc",
        raw_text="review this PR https://github.com/FlexyPe/flexype-adhocs/pull/91",
        cleaned_intent="review this PR https://github.com/FlexyPe/flexype-adhocs/pull/91",
    )

    with patch("backend.ingress.pr_analysis.analyze_pull_request") as mock_analyze:
        mock_analyze.return_value = ("**Summary**\nAdds SQS consumer support.", {"repo": "FlexyPe/flexype-adhocs", "number": 91})
        with patch("backend.agent.loop.run_agent_loop") as mock_loop:
            response = processor.process(task)

    assert "SQS consumer" in response.payload.data["text"]
    mock_analyze.assert_called_once()
    mock_loop.assert_not_called()


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
        raw_text="summarize https://github.com/FlexyPe/flexype-adhocs/pull/91",
        cleaned_intent="summarize https://github.com/FlexyPe/flexype-adhocs/pull/91",
    )

    pr_detail = {
        "number": 91,
        "title": "SQS Consumer",
        "repo": "FlexyPe/flexype-adhocs",
        "url": "https://github.com/FlexyPe/flexype-adhocs/pull/91",
        "body": "Adds consumer",
        "head": "feature/sqs",
        "base": "main",
    }

    with patch("backend.tools.git_api.GitApiClient") as mock_client_cls:
        mock_client = mock_client_cls.from_alfred_config.return_value
        mock_client.get_pr.return_value = pr_detail
        with patch("backend.ingress.pr_analysis.analyze_pull_request") as mock_analyze:
            with patch.object(processor, "_summarize_pr", return_value="Short summary from description."):
                response = processor.process(task)

    mock_analyze.assert_not_called()
    assert "Short summary" in response.payload.data["text"]
