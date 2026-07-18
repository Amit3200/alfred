"""Tests for web_search tool and providers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from backend.health import check_web_search
from backend.integrations.web.search import WebSearchClient
from backend.models.config import AlfredConfig, WebSearchConfig
from backend.tools.git_api import build_git_tool_registry
from backend.tools.result import ToolResult


def _config(**overrides) -> AlfredConfig:
    defaults = dict(enabled=True, provider="duckduckgo", max_results=5, api_key="")
    defaults.update(overrides)
    config = AlfredConfig()
    config.web_search = WebSearchConfig(**defaults)
    return config


@patch("duckduckgo_search.DDGS")
def test_duckduckgo_search_returns_results(mock_ddgs_cls):
    mock_ddgs = MagicMock()
    mock_ddgs.__enter__.return_value = mock_ddgs
    mock_ddgs.text.return_value = [
        {"title": "FastAPI docs", "href": "https://fastapi.tiangolo.com", "body": "Modern Python API framework."},
    ]
    mock_ddgs_cls.return_value = mock_ddgs

    client = WebSearchClient(_config().web_search)
    data = client.search("FastAPI dependency injection")

    assert data["provider"] == "duckduckgo"
    assert data["query"] == "FastAPI dependency injection"
    assert len(data["results"]) == 1
    assert data["results"][0]["url"] == "https://fastapi.tiangolo.com"


@patch("backend.integrations.web.search.requests.post")
def test_tavily_search_includes_answer(mock_post):
    mock_post.return_value = MagicMock(
        raise_for_status=MagicMock(),
        json=MagicMock(
            return_value={
                "answer": "Use Depends() for injection.",
                "results": [
                    {
                        "title": "Dependencies",
                        "url": "https://fastapi.tiangolo.com/tutorial/dependencies/",
                        "content": "FastAPI dependency injection guide.",
                    }
                ],
            }
        ),
    )

    client = WebSearchClient(_config(provider="tavily", api_key="tvly-test").web_search)
    data = client.search("FastAPI Depends")

    assert data["provider"] == "tavily"
    assert data["answer"] == "Use Depends() for injection."
    assert data["results"][0]["snippet"] == "FastAPI dependency injection guide."
    mock_post.assert_called_once()


def test_tavily_requires_api_key():
    client = WebSearchClient(_config(provider="tavily", api_key="").web_search)
    with pytest.raises(RuntimeError, match="Tavily API key"):
        client.search("anything")


@patch("backend.tools.web_search_tool.WebSearchClient")
def test_web_search_tool_registration(mock_client_cls):
    mock_client = MagicMock()
    mock_client.search.return_value = {
        "query": "pytest fixtures",
        "provider": "duckduckgo",
        "results": [{"title": "Fixtures", "url": "https://docs.pytest.org", "snippet": "..."}],
    }
    mock_client_cls.from_config.return_value = mock_client

    registry = build_git_tool_registry(_config())
    result = registry.run("web_search", {"query": "pytest fixtures"}, allowed=["web_search"])

    assert isinstance(result, ToolResult)
    assert result.kind == "web_search"
    assert result.data["results"][0]["title"] == "Fixtures"


def test_web_search_tool_disabled_when_integration_off():
    registry = build_git_tool_registry(_config(enabled=False))
    result = registry.run("web_search", {"query": "test"}, allowed=["web_search"])
    assert result.kind == "error"
    assert "unknown tool" in (result.data.get("message") or "").lower()


@patch("backend.integrations.web.search.WebSearchClient")
def test_check_web_search_ok(mock_client_cls):
    mock_client = MagicMock()
    mock_client.ping.return_value = {"provider": "duckduckgo", "result_count": 1}
    mock_client_cls.from_config.return_value = mock_client

    result = check_web_search(_config())
    assert result["ok"] is True
    assert "duckduckgo" in result["message"]


def test_check_web_search_skipped_when_disabled():
    result = check_web_search(_config(enabled=False))
    assert result["skipped"] is True
