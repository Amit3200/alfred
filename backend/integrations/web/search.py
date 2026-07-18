"""Web search providers — DuckDuckGo (default) and Tavily (API key)."""

from __future__ import annotations

import logging
from typing import Any

import requests

from backend.models.config import WebSearchConfig

logger = logging.getLogger(__name__)


class WebSearchClient:
    def __init__(self, config: WebSearchConfig) -> None:
        self._config = config

    @classmethod
    def from_config(cls, config: WebSearchConfig) -> WebSearchClient:
        return cls(config)

    def search(self, query: str, *, max_results: int | None = None) -> dict[str, Any]:
        text = (query or "").strip()
        if not text:
            raise ValueError("query is required")
        limit = max(1, min(int(max_results or self._config.max_results), 20))
        provider = (self._config.provider or "duckduckgo").lower()
        if provider == "tavily":
            return self._search_tavily(text, max_results=limit)
        return self._search_duckduckgo(text, max_results=limit)

    def ping(self) -> dict[str, Any]:
        data = self.search("Alfred agent test", max_results=1)
        return {"provider": data.get("provider"), "result_count": len(data.get("results") or [])}

    def _search_duckduckgo(self, query: str, *, max_results: int) -> dict[str, Any]:
        try:
            from duckduckgo_search import DDGS
        except ImportError as exc:
            raise RuntimeError(
                "duckduckgo-search is not installed. Run: uv sync --extra web"
            ) from exc

        rows: list[dict[str, str]] = []
        try:
            with DDGS() as ddgs:
                for item in ddgs.text(query, max_results=max_results):
                    if not isinstance(item, dict):
                        continue
                    rows.append(
                        {
                            "title": str(item.get("title") or "").strip(),
                            "url": str(item.get("href") or item.get("url") or "").strip(),
                            "snippet": str(item.get("body") or item.get("snippet") or "").strip(),
                        }
                    )
        except Exception as exc:
            logger.exception("DuckDuckGo search failed")
            raise RuntimeError(f"Web search failed: {exc}") from exc

        return {
            "query": query,
            "provider": "duckduckgo",
            "results": [row for row in rows if row.get("title") or row.get("snippet")],
        }

    def _search_tavily(self, query: str, *, max_results: int) -> dict[str, Any]:
        api_key = (self._config.api_key or "").strip()
        if not api_key:
            raise RuntimeError("Tavily API key not configured — add it under Admin → Secrets.")

        try:
            response = requests.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": api_key,
                    "query": query,
                    "max_results": max_results,
                    "include_answer": True,
                    "search_depth": "basic",
                },
                timeout=30,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            logger.exception("Tavily search failed")
            raise RuntimeError(f"Tavily search failed: {exc}") from exc

        rows: list[dict[str, str]] = []
        for item in payload.get("results") or []:
            if not isinstance(item, dict):
                continue
            rows.append(
                {
                    "title": str(item.get("title") or "").strip(),
                    "url": str(item.get("url") or "").strip(),
                    "snippet": str(item.get("content") or "").strip(),
                }
            )

        return {
            "query": query,
            "provider": "tavily",
            "answer": str(payload.get("answer") or "").strip(),
            "results": rows,
        }
