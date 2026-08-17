"""Graphify query tool for investigation skills."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.ai.base import ToolSchema
from backend.context.graphify import query_graph
from backend.models.config import AlfredConfig
from backend.tools.base.function_tool import FunctionTool
from backend.tools.base.tool import BaseTool, ToolContext
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


def query_graph_tool(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    question = str(args.get("question") or "").strip()
    if not question:
        return ToolResult.error("question is required.")
    if ctx.data_dir is None:
        return ToolResult.error("data_dir is required for query_graph.")
    repo = str(args.get("repo") or "").strip() or None
    budget = args.get("budget")
    budget_int = int(budget) if budget is not None else 1500
    result = query_graph(
        ctx.data_dir,
        ctx.config.git,
        question,
        repo=repo,
        budget=budget_int,
    )
    if not result.get("ok"):
        return ToolResult(
            kind="graph_query",
            data={
                "repo": repo or "main",
                "question": question,
                "answer": (
                    f"Graphify is currently unavailable: {result.get('error')}. "
                    "Please fall back to standard codebase search tools (grep_repo, read_file)."
                ),
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


def graphify_tools() -> list[BaseTool]:
    return [
        FunctionTool(
            name="query_graph",
            capability="git.repo.read",
            operation="query_graph",
            domain="git",
            schema=QUERY_GRAPH,
            run_fn=query_graph_tool,
            produces=("graph_answer",),
            next_tools=("grep_repo", "read_file"),
        )
    ]


def register_graphify_tools(
    registry: ToolRegistry,
    *,
    config: AlfredConfig,
    data_dir: Path,
) -> None:
    if not config.git.graphify_enabled:
        return
    registry.alfred_config = config
    registry.data_dir = data_dir
    from backend.tools.git.bundle import GraphifyToolBundle

    GraphifyToolBundle().register(registry)
