"""Invoke Alfred LangGraph for tool-routed investigation tasks."""

from __future__ import annotations

import logging
from typing import Any

from backend.models.response import AssistantResponse
from backend.orchestrator.graph.build import get_compiled_graph
from backend.orchestrator.graph.runtime import GraphRuntime
from backend.orchestrator.graph.serialize import goal_spec_to_dict
from backend.orchestrator.graph.state import AlfredGraphState

logger = logging.getLogger(__name__)


def run_investigation_graph(
    processor: Any,
    skill: Any,
    messages: list[Any],
    *,
    provider: Any,
    model: str,
    task: Any,
    session: Any,
    route_context: Any,
    scoped_tools: list[str] | None = None,
    goal_spec: Any | None = None,
    manifest_text: str = "",
) -> tuple[AssistantResponse, dict[str, Any] | None]:
    """Run plan → validate → direct/worker → ground → reply via LangGraph."""
    data_dir = processor._data_dir_path()
    use_checkpoint = bool(processor.config.routing.langgraph_checkpoint)
    compiled = get_compiled_graph(use_checkpoint, str(data_dir) if use_checkpoint else "")

    runtime = GraphRuntime(
        processor=processor,
        skill=skill,
        messages=messages,
        provider=provider,
        model=model,
        task=task,
        session=session,
        route_context=route_context,
        goal_spec=goal_spec,
        scoped_tools=scoped_tools,
        manifest_text=manifest_text,
    )

    initial: AlfredGraphState = {
        "task_id": task.id,
        "intent": task.cleaned_intent,
        "skill_name": skill.name,
        "goal_spec": goal_spec_to_dict(goal_spec),
        "scoped_tools": scoped_tools or [],
        "manifest_text": manifest_text,
    }

    thread_id = f"{task.source}:{task.channel_id}:{task.thread_ts or task.id}"
    invoke_config: dict[str, Any] = {
        "configurable": {"runtime": runtime, "thread_id": thread_id},
    }

    logger.info("LangGraph investigation start task=%s skill=%s", task.id, skill.name)
    final = compiled.invoke(initial, config=invoke_config)

    kind = final.get("response_kind") or "text"
    data = dict(final.get("response_data") or {})
    patch = final.get("metadata_patch")

    if kind == "error":
        return AssistantResponse.error(str(data.get("message") or data.get("text") or "Error")), patch
    if kind != "text":
        return AssistantResponse.structured(kind, data), patch

    text = str(final.get("raw_reply") or data.get("text") or "")
    if not final.get("grounding_passed", True):
        logger.info("LangGraph grounding issues: %s", final.get("grounding_issues"))
    processor._record_routing_trace(
        task,
        skill=skill,
        graph_final=final,
        routing_strategy=str((final.get("tool_plan") or {}).get("strategy") or "langgraph"),
    )
    return AssistantResponse.from_text(text), patch
