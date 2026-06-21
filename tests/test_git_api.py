"""Tests for GitHub API client."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from backend.git.api import GitApiClient, split_repo_slug
from backend.models.config import GitConfig


def test_split_repo_slug():
    assert split_repo_slug("myorg/backend") == ("myorg", "backend")


def test_list_available_repos_merges_configured_and_remote():
    config = GitConfig(
        enabled=True,
        provider="github",
        token="ghp_test",
        default_org="FlexyPe",
        repos=["FlexyPe/cipher"],
    )
    client = GitApiClient(config)
    client._impl = MagicMock()
    client._impl.list_accessible_repos.return_value = [
        "FlexyPe/cipher",
        "FlexyPe/other",
    ]
    payload = client.list_available_repos()
    assert payload["source"] == "org"
    assert payload["org"] == "FlexyPe"
    assert payload["repos"] == ["FlexyPe/cipher", "FlexyPe/other"]


@patch("backend.git.api.requests.Session")
def test_list_available_repos_without_token(mock_session_cls):
    config = GitConfig(
        enabled=True,
        provider="github",
        token="",
        default_org="FlexyPe",
        repos=["FlexyPe/cipher"],
    )
    with pytest.raises(RuntimeError, match="Git token"):
        GitApiClient(config)


@patch("backend.git.api.requests.Session")
def test_github_list_my_prs(mock_session_cls):
    session = MagicMock()
    mock_session_cls.return_value = session
    session.request.side_effect = [
        MagicMock(
            status_code=200,
            content=b'{"login":"alice"}',
            json=lambda: {"login": "alice"},
        ),
        MagicMock(
            status_code=200,
            content=b"{}",
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
    session.request.return_value = MagicMock(
        status_code=200,
        content=b"[]",
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
    session.request.return_value = MagicMock(
        status_code=200,
        content=b"{}",
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
    session.request.return_value = MagicMock(
        status_code=200,
        content=b"[]",
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


@patch("backend.git.api.requests.Session")
def test_github_create_issue_comment(mock_session_cls):
    session = MagicMock()
    mock_session_cls.return_value = session
    session.request.return_value = MagicMock(
        status_code=201,
        content=b'{"id":99}',
        json=lambda: {"id": 99, "body": "Review complete"},
    )

    config = GitConfig(enabled=True, provider="github", token="ghp_test")
    client = GitApiClient(config)
    result = client.create_issue_comment("myorg/backend", 3, "Review complete")

    assert result["id"] == 99
    call = session.request.call_args
    assert call.args[0] == "POST"
    assert "/issues/3/comments" in call.args[1]
    assert call.kwargs["json"] == {"body": "Review complete"}


@patch("backend.git.api.requests.Session")
def test_github_create_issue_comment_reaction(mock_session_cls):
    session = MagicMock()
    mock_session_cls.return_value = session
    session.request.return_value = MagicMock(
        status_code=201,
        content=b'{"id":1}',
        json=lambda: {"id": 1, "content": "eyes"},
    )

    config = GitConfig(enabled=True, provider="github", token="ghp_test")
    client = GitApiClient(config)
    result = client.create_issue_comment_reaction("myorg/backend", 99, "eyes")

    assert result["content"] == "eyes"
    call = session.request.call_args
    assert call.args[0] == "POST"
    assert "/issues/comments/99/reactions" in call.args[1]
    assert call.kwargs["json"] == {"content": "eyes"}
