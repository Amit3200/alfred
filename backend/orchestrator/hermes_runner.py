"""Hermes autonomous agent loop runner - handles tool execution and intermediate learning logs."""

from __future__ import annotations

import json
import logging
from typing import Any

from backend.ai.base import LLMProvider, LLMResponse, Message, ToolCall
from backend.routing.git_direct import parse_text_tool_call, strip_text_tool_markup
from backend.tools.registry import ToolRegistry
from backend.observability.checkpoint import log_checkpoint

logger = logging.getLogger(__name__)

from backend.orchestrator.prompts import HERMES_SYSTEM_INSTRUCTIONS

def run_hermes_loop(
    provider: LLMProvider,
    messages: list[Message],
    registry: ToolRegistry,
    allowed_tools: list[str],
    *,
    model: str | None = None,
    max_iterations: int = 20,
    session: Any | None = None,
    git: Any | None = None,
) -> str:
    """Run Hermes tool-augmented loop until final answer is reached or max_iterations exceeded."""
    conversation = list(messages)
    if conversation and conversation[0].role == "system":
        conversation[0] = Message(
            role="system",
            content=f"{conversation[0].content}\n\n{HERMES_SYSTEM_INSTRUCTIONS}"
        )
    else:
        conversation.insert(0, Message(role="system", content=HERMES_SYSTEM_INSTRUCTIONS))

    tool_schemas = registry.get_schemas(allowed_tools)
    if not tool_schemas:
        raise RuntimeError("No tools available for the matched skill.")

    from backend.observability.checkpoint import current_task_id, current_data_dir
    task_id = current_task_id.get()
    data_dir = current_data_dir.get()

    def get_plan_context() -> str | None:
        if task_id:
            from backend.orchestrator.planning import resolve_plan_for_task

            return resolve_plan_for_task(task_id, session=session, data_dir=data_dir)
        return None

    for iteration in range(max_iterations):
        logger.debug("Hermes loop iteration %d", iteration + 1)

        plan_content = get_plan_context()
        if plan_content:
            found = False
            for idx, msg in enumerate(conversation):
                if msg.role == "system" and "## Task Plan Checklist" in msg.content:
                    conversation[idx] = Message(
                        role="system",
                        content=f"{HERMES_SYSTEM_INSTRUCTIONS}\n\n## Task Plan Checklist\n{plan_content}"
                    )
                    found = True
                    break
            if not found:
                conversation.insert(1, Message(
                    role="system",
                    content=f"## Task Plan Checklist\n{plan_content}"
                ))

        log_checkpoint(
            "hermes_loop_iteration",
            f"iteration_{iteration + 1}",
            "started"
        )
        
        try:
            response = provider.chat(conversation, tools=tool_schemas, model=model)
        except Exception as e:
            log_checkpoint(
                "hermes_loop_iteration",
                f"iteration_{iteration + 1}",
                "error",
                error=e
            )
            raise

        if response.tool_calls:
            assistant_msg = Message(
                role="assistant",
                content=response.content or "",
                tool_calls=response.tool_calls
            )
            conversation.append(assistant_msg)
            
            for tool_call in response.tool_calls:
                observation = _execute_hermes_tool(
                    registry,
                    tool_call.name,
                    tool_call.arguments,
                    allowed=allowed_tools,
                    session=session,
                    git=git,
                )
                conversation.append(
                    Message(
                        role="tool",
                        content=observation,
                        tool_call_id=tool_call.id,
                        name=tool_call.name,
                    )
                )
                # Update checklist progress dynamically
                if task_id and data_dir:
                    try:
                        from backend.config_manager import ConfigManager
                        from backend.orchestrator.planning import update_plan_progress
                        config, _ = ConfigManager(data_dir).load_merged()
                        last_action = f"Called tool {tool_call.name} with args {tool_call.arguments}"
                        update_plan_progress(task_id, last_action, observation, config, data_dir)
                    except Exception:
                        logger.exception("Failed to update plan progress in Hermes loop")
            
            log_checkpoint(
                "hermes_loop_iteration",
                f"iteration_{iteration + 1}_tool_called",
                "completed"
            )
            continue

        content = (response.content or "").strip()
        if content:
            parsed = parse_text_tool_call(content)
            if parsed:
                name, arguments = parsed
                if name in allowed_tools:
                    tool_id = f"hermes_text_call_{iteration + 1}"
                    logger.info("Hermes executing text-emitted tool call: %s", name)
                    summary = strip_text_tool_markup(content) or f"Calling {name}..."
                    conversation.append(
                        Message(
                            role="assistant",
                            content=summary,
                            tool_calls=[ToolCall(id=tool_id, name=name, arguments=arguments)],
                        )
                    )
                    observation = _execute_hermes_tool(
                        registry,
                        name,
                        arguments,
                        allowed=allowed_tools,
                        session=session,
                        git=git,
                    )
                    conversation.append(
                        Message(
                            role="tool",
                            content=observation,
                            tool_call_id=tool_id,
                            name=name,
                        )
                    )
                    # Update checklist progress dynamically
                    if task_id and data_dir:
                        try:
                            from backend.config_manager import ConfigManager
                            from backend.orchestrator.planning import update_plan_progress
                            config, _ = ConfigManager(data_dir).load_merged()
                            last_action = f"Called tool {name} with args {arguments}"
                            update_plan_progress(task_id, last_action, observation, config, data_dir)
                        except Exception:
                            logger.exception("Failed to update plan progress in Hermes loop (text-tool)")
                    log_checkpoint(
                        "hermes_loop_iteration",
                        f"iteration_{iteration + 1}_text_tool_called",
                        "completed"
                    )
                    continue
            
            log_checkpoint(
                "hermes_loop_iteration",
                f"iteration_{iteration + 1}_final_answer",
                "completed"
            )
            return content

        log_checkpoint(
            "hermes_loop_iteration",
            f"iteration_{iteration + 1}_no_response",
            "completed"
        )
        return (
            "I ran the Hermes available tools but could not form a final answer. "
            "Try rephrasing or check integration settings."
        )

def _execute_hermes_tool(
    registry: ToolRegistry,
    name: str,
    arguments: dict[str, Any],
    *,
    allowed: list[str],
    session: Any | None = None,
    git: Any | None = None,
) -> str:
    """Execute a single tool inside the Hermes execution environment."""
    from backend.agent.loop import _execute_tool
    return _execute_tool(registry, name, arguments, allowed=allowed, session=session, git=git)
