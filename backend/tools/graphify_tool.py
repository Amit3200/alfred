"""Graphify query tool for investigation skills."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.ai.base import ToolSchema
from backend.context.graphify import query_graph
from backend.models.config import AlfredConfig
from backend.tools.registry import ToolRegistry
from backend.tools.result import ToolResult

QUERY_GRAPH = ToolSchema(
    name="query_graph",
    description=(
        "Query a Graphify knowledge graph — imports, callers, communities, and structural relationships. "
        "Prefer this before grep when tracing stack traces or blast radius. "
        "Use repo for doc/code graphs beyond main_repo when configured."
    ),
    parameters={
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "Natural language question about code structure or relationships.",
            },
            "repo": {
                "type": "string",
                "description": "Repository slug (defaults to git.main_repo).",
            },
            "budget": {
                "type": "integer",
                "description": "Max graph traversal budget (default 1500).",
            },
        },
        "required": ["question"],
    },
)


def register_graphify_tools(
    registry: ToolRegistry,
    *,
    config: AlfredConfig,
    data_dir: Path,
) -> None:
    if not config.git.graphify_enabled:
        return

    def query_graph_handler(args: dict[str, Any]) -> ToolResult:
        question = str(args.get("question") or "").strip()
        if not question:
            return ToolResult.error("question is required.")
        repo = str(args.get("repo") or "").strip() or None
        budget = args.get("budget")
        budget_int = int(budget) if budget is not None else 1500
        result = query_graph(
            data_dir,
            config.git,
            question,
            repo=repo,
            budget=budget_int,
        )
        if not result.get("ok"):
            # Return a friendly fallback answer to let the agent know to use grep_repo or read_file
            return ToolResult(
                kind="graph_query",
                data={
                    "repo": repo or "main",
                    "question": question,
                    "answer": f"Graphify is currently unavailable: {result.get('error')}. Please fall back to standard codebase search tools (grep_repo, read_file).",
                    "source": "fallback_system",
                },
            )
        return ToolResult(
            kind="graph_query",
            data={
                "repo": result.get("repo"),
                "question": result.get("question"),
                "answer": result.get("answer"),
                "source": result.get("source"),
            },
        )

    registry.register(QUERY_GRAPH, query_graph_handler)
