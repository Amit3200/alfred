"""Tests for GitHub API client."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from backend.git.api import GitApiClient, split_repo_slug
from backend.models.config import GitConfig


def test_split_repo_slug():
    assert split_repo_slug("myorg/backend") == ("myorg", "backend")


def test_split_repo_slug_invalid():
    with pytest.raises(ValueError):
        split_repo_slug("backend")


@patch("backend.git.api.requests.Session")
def test_github_list_my_prs(mock_session_cls):
    session = MagicMock()
    mock_session_cls.return_value = session
    session.get.side_effect = [
        MagicMock(
            status_code=200,
            json=lambda: {"login": "alice"},
        ),
        MagicMock(
            status_code=200,
            json=lambda: {
                "items": [
                    {
                        "number": 7,
                        "title": "Fix orders",
                        "state": "open",
                        "html_url": "https://github.com/myorg/backend/pull/7",
                        "repository_url": "https://api.github.com/repos/myorg/backend",
                        "draft": False,
                    }
                ]
            },
        ),
    ]

    config = GitConfig(enabled=True, provider="github", token="ghp_test")
    client = GitApiClient(config)
    prs = client.list_my_prs(state="open")

    assert len(prs) == 1
    assert prs[0].number == 7
    assert prs[0].repo == "myorg/backend"
    assert "Fix orders" in prs[0].title


@patch("backend.git.api.requests.Session")
def test_github_list_prs(mock_session_cls):
    session = MagicMock()
    mock_session_cls.return_value = session
    session.get.return_value = MagicMock(
        status_code=200,
        json=lambda: [
            {
                "number": 3,
                "title": "Add metrics",
                "state": "open",
                "html_url": "https://github.com/myorg/backend/pull/3",
                "user": {"login": "bob"},
                "draft": False,
            }
        ],
    )

    config = GitConfig(enabled=True, provider="github", token="ghp_test")
    client = GitApiClient(config)
    prs = client.list_prs("myorg/backend")

    assert len(prs) == 1
    assert prs[0].author == "bob"


@patch("backend.git.api.requests.Session")
def test_github_get_pr(mock_session_cls):
    session = MagicMock()
    mock_session_cls.return_value = session
    session.get.return_value = MagicMock(
        status_code=200,
        json=lambda: {
            "number": 3,
            "title": "Add metrics",
            "state": "open",
            "html_url": "https://github.com/myorg/backend/pull/3",
            "user": {"login": "bob"},
            "body": "Details",
            "head": {"ref": "feature"},
            "base": {"ref": "main"},
        },
    )

    config = GitConfig(enabled=True, provider="github", token="ghp_test")
    client = GitApiClient(config)
    data = client.get_pr("myorg/backend", 3)

    assert data["number"] == 3
    assert data["head"] == "feature"


@patch("backend.git.api.requests.Session")
def test_github_get_pr_files(mock_session_cls):
    session = MagicMock()
    mock_session_cls.return_value = session
    session.get.return_value = MagicMock(
        status_code=200,
        json=lambda: [
            {
                "filename": "src/consumer.py",
                "status": "added",
                "additions": 42,
                "deletions": 0,
                "changes": 42,
                "patch": "@@ -0,0 +1,3 @@\n+line",
            }
        ],
    )

    config = GitConfig(enabled=True, provider="github", token="ghp_test")
    client = GitApiClient(config)
    files = client.get_pr_files("myorg/backend", 3)

    assert len(files) == 1
    assert files[0]["filename"] == "src/consumer.py"
    assert files[0]["status"] == "added"
    assert "line" in files[0]["patch"]
