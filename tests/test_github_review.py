"""Tests for GitHub PR review CLI helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from backend.github.review import parse_pr_ref, run_github_pr_review
from backend.models.config import AlfredConfig, GitConfig
from backend.models.response import AssistantResponse


def test_parse_pr_ref_url():
    repo, number, url = parse_pr_ref("https://github.com/AcmeCorp/platform/pull/2047")
    assert repo == "AcmeCorp/platform"
    assert number == 2047
    assert url.endswith("/pull/2047")


def test_parse_pr_ref_hash():
    repo, number, url = parse_pr_ref("AcmeCorp/platform#2047")
    assert repo == "AcmeCorp/platform"
    assert number == 2047
    assert "AcmeCorp/platform/pull/2047" in url


def test_parse_pr_ref_invalid():
    with pytest.raises(ValueError):
        parse_pr_ref("not-a-pr")


def test_run_github_pr_review_posts_rendered_body():
    manager = MagicMock()
    config = AlfredConfig(git=GitConfig(enabled=True, provider="github", token="ghp_test"))
    manager.load_merged.return_value = (config, MagicMock())
    manager.data_dir = MagicMock()

    review_text = "## 1. Executive Summary\n**PR Objective:** Improve webhook logging"
    mock_processor = MagicMock()
    mock_processor.process.return_value = AssistantResponse.from_text(review_text)

    with patch("backend.github.review.post_pull_request_comment") as post:
        body, status = run_github_pr_review(
            manager,
            "AcmeCorp/platform#7",
            processor_factory=lambda: mock_processor,
        )

    assert "Executive Summary" in body
    assert "Improve webhook logging" in body
    assert status == "posted comment on AcmeCorp/platform#7"
    post.assert_called_once()
    assert post.call_args.kwargs["body"] == body
    assert post.call_args.kwargs["number"] == 7
