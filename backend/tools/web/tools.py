"""Web search FunctionTool."""

from __future__ import annotations

from typing import Any

from backend.ai.base import ToolSchema
from backend.integrations.web.search import WebSearchClient
from backend.tools.base.function_tool import FunctionTool
from backend.tools.base.tool import BaseTool, ToolContext
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


def web_search(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    query = str(args.get("query") or "").strip()
    if not query:
        return ToolResult.error("query is required.")
    max_results = args.get("max_results")
    client = WebSearchClient.from_config(ctx.config.web_search)
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


def web_tools() -> list[BaseTool]:
    return [
        FunctionTool(
            name="web_search",
            capability="web.search",
            operation="search",
            domain="web",
            schema=WEB_SEARCH,
            run_fn=web_search,
            produces=("results",),
        )
    ]

