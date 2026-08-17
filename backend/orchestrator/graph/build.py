"""Build and compile the Alfred LangGraph orchestration graph."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from langgraph.graph import END, START, StateGraph

from backend.orchestrator.graph.edges import route_after_direct, route_after_validate
from backend.orchestrator.graph.nodes import (
    extract_entities_node,
    format_reply_node,
    missing_tools_node,
    plan_tools_node,
    run_worker_node,
    try_direct_node,
    validate_goal_node,
    validate_plan_node,
)
from backend.orchestrator.graph.state import AlfredGraphState


def build_alfred_graph():
    graph = StateGraph(AlfredGraphState)

    graph.add_node("extract_entities", extract_entities_node)
    graph.add_node("plan_tools", plan_tools_node)
    graph.add_node("validate_plan", validate_plan_node)
    graph.add_node("try_direct", try_direct_node)
    graph.add_node("run_worker", run_worker_node)
    graph.add_node("missing_tools", missing_tools_node)
    graph.add_node("validate_goal", validate_goal_node)
    graph.add_node("format_reply", format_reply_node)

    graph.add_edge(START, "extract_entities")
    graph.add_edge("extract_entities", "plan_tools")
    graph.add_edge("plan_tools", "validate_plan")
    graph.add_conditional_edges(
        "validate_plan",
        route_after_validate,
        {
            "missing_tools": "missing_tools",
            "try_direct": "try_direct",
            "run_worker": "run_worker",
        },
    )
    graph.add_conditional_edges(
        "try_direct",
        route_after_direct,
        {
            "format_reply": "format_reply",
            "run_worker": "run_worker",
        },
    )
    graph.add_edge("run_worker", "validate_goal")
    graph.add_edge("missing_tools", "format_reply")
    graph.add_edge("validate_goal", "format_reply")
    graph.add_edge("format_reply", END)

    return graph


@lru_cache(maxsize=4)
def get_compiled_graph(use_checkpoint: bool = False, checkpoint_data_dir: str = ""):
    """Return compiled graph; SQLite checkpointer when enabled."""
    graph = build_alfred_graph()
    if use_checkpoint:
        if checkpoint_data_dir:
            from backend.orchestrator.graph.checkpoint import get_langgraph_checkpointer

            checkpointer = get_langgraph_checkpointer(Path(checkpoint_data_dir))
            return graph.compile(checkpointer=checkpointer)
        from langgraph.checkpoint.memory import MemorySaver

        return graph.compile(checkpointer=MemorySaver())
    return graph.compile()
