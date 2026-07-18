"""Web search tool — external research for errors, docs, and product facts."""

from __future__ import annotations

from typing import Any

from backend.ai.base import ToolSchema
from backend.integrations.web.search import WebSearchClient
from backend.models.config import AlfredConfig
from backend.tools.registry import ToolRegistry
from backend.tools.result import ToolResult

WEB_SEARCH = ToolSchema(
    name="web_search",
    description=(
        "Search the public web for documentation, error messages, library behavior, "
        "release notes, or general facts. Use when the answer is not in the repo, JIRA, or AWS."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query — be specific (product, error text, version).",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum results to return (default from config, max 20).",
            },
        },
        "required": ["query"],
    },
)


def register_web_search_tools(registry: ToolRegistry, config: AlfredConfig) -> None:
    if not config.web_search.enabled:
        return

    client = WebSearchClient.from_config(config.web_search)

    def web_search_handler(args: dict[str, Any]) -> ToolResult:
        query = str(args.get("query") or "").strip()
        if not query:
            return ToolResult.error("query is required.")
        max_results = args.get("max_results")
        try:
            data = client.search(
                query,
                max_results=int(max_results) if max_results is not None else None,
            )
            return ToolResult.web_search(data)
        except ValueError as exc:
            return ToolResult.error(str(exc))
        except RuntimeError as exc:
            return ToolResult.error(str(exc))
        except Exception as exc:
            return ToolResult.error(f"Web search failed: {exc}")

    registry.register(WEB_SEARCH, web_search_handler)
