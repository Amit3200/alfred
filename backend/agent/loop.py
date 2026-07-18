"""ReAct agent loop — LLM tool calls until a final answer."""

from __future__ import annotations

import json
import logging
from typing import Any

from backend.ai.base import LLMProvider, LLMResponse, Message, ToolCall
from backend.routing.git_direct import parse_text_tool_call, strip_text_tool_markup
from backend.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

DEFAULT_MAX_ITERATIONS = 20


def run_agent_loop(
    provider: LLMProvider,
    messages: list[Message],
    registry: ToolRegistry,
    allowed_tools: list[str],
    *,
    model: str | None = None,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    session: Any | None = None,
    git: Any | None = None,
) -> str:
    """Run tool-augmented chat until the model returns text or limits are hit."""
    tool_schemas = registry.get_schemas(allowed_tools)
    if not tool_schemas:
        raise RuntimeError("No tools available for the matched skill.")

    conversation = list(messages)

    from backend.observability.checkpoint import current_task_id, current_data_dir
    from backend.orchestrator.task_cancel import raise_if_cancelled

    task_id = current_task_id.get()
    data_dir = current_data_dir.get()

    def get_plan_context() -> str | None:
        if task_id:
            from backend.orchestrator.planning import resolve_plan_for_task

            return resolve_plan_for_task(task_id, session=session, data_dir=data_dir)
        return None

    for iteration in range(max_iterations):
        raise_if_cancelled(data_dir, task_id)
        logger.debug("Agent loop iteration %d", iteration + 1)

        plan_content = get_plan_context()
        if plan_content:
            found = False
            for idx, msg in enumerate(conversation):
                if msg.role == "system" and "## Task Plan Checklist" in msg.content:
                    conversation[idx] = Message(
                        role="system",
                        content=f"## Task Plan Checklist\n{plan_content}"
                    )
                    found = True
                    break
            if not found:
                conversation.insert(1, Message(
                    role="system",
                    content=f"## Task Plan Checklist\n{plan_content}"
                ))

        response = provider.chat(conversation, tools=tool_schemas, model=model)

        if response.tool_calls:
            conversation.append(_assistant_tool_message(response))
            for tool_call in response.tool_calls:
                observation = _execute_tool(
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
                        logger.exception("Failed to update plan progress in ReAct loop")
            continue

        content = (response.content or "").strip()
        if content:
            parsed = parse_text_tool_call(content)
            if parsed:
                name, arguments = parsed
                if name in allowed_tools:
                    tool_id = f"text_call_{iteration + 1}"
                    logger.info("Executing text-emitted tool call: %s", name)
                    summary = strip_text_tool_markup(content) or f"Calling {name}..."
                    conversation.append(
                        Message(
                            role="assistant",
                            content=summary,
                            tool_calls=[ToolCall(id=tool_id, name=name, arguments=arguments)],
                        )
                    )
                    observation = _execute_tool(
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
                    continue
            return content

        return (
            "I ran the available tools but could not form a final answer. "
            "Try rephrasing or check Git integration settings."
        )

    synthesized = _synthesize_final_answer(provider, conversation, model=model)
    if synthesized:
        return synthesized

    return (
        "I searched the codebase but ran out of investigation steps before I could "
        "finish. Try a narrower question (e.g. a specific function, file, or error message)."
    )


def _synthesize_final_answer(
    provider: LLMProvider,
    conversation: list[Message],
    *,
    model: str | None = None,
) -> str | None:
    """One tool-free LLM pass to answer from gathered tool results."""
    synthesis_messages = [
        *conversation,
        Message(
            role="user",
            content=(
                "You reached the investigation step limit. Using only the tool results "
                "and context above, give the user a direct answer to their question. "
                "Cite file paths when relevant. If evidence is incomplete, summarize "
                "what you found and what remains unclear — do not ask them to restate "
                "the repo name if it already appears in this thread."
            ),
        ),
    ]
    try:
        response = provider.chat(synthesis_messages, model=model)
    except Exception:
        logger.exception("Synthesis pass failed")
        return None

    if response.tool_calls:
        return None

    content = strip_text_tool_markup((response.content or "").strip()).strip()
    return content or None


def _assistant_tool_message(response: LLMResponse) -> Message:
    summary = (response.content or "").strip()
    if not summary:
        names = ", ".join(tc.name for tc in response.tool_calls)
        summary = f"Calling tools: {names}"
    return Message(
        role="assistant",
        content=summary,
        tool_calls=list(response.tool_calls),
    )


def serialize_tool_arguments(arguments: dict) -> str:
    return json.dumps(arguments)


def _execute_tool(
    registry: ToolRegistry,
    name: str,
    arguments: dict,
    *,
    allowed: list[str],
    session: Any | None = None,
    git: Any | None = None,
) -> str:
    from backend.observability.checkpoint import log_checkpoint

    checkpoint_name = f"{name}_tool_call"
    if name.startswith("jira") or name in ("add_jira_comment", "link_jira_issue", "get_jira_issue", "transition_jira_issue"):
        checkpoint_name = "jira_tool_call"
    elif name.startswith(("git", "github")):
        checkpoint_name = "git_tool_call"
    elif name.startswith(("athena", "cloudwatch")):
        checkpoint_name = "aws_tool_call"

    log_checkpoint(checkpoint_name, name, "started")
    try:
        git_cfg = git or getattr(registry, "git_config", None)
        if git_cfg is not None:
            result = registry.run_normalized(
                name,
                arguments,
                allowed=allowed,
                git=git_cfg,
                session=session,
            )
        else:
            result = registry.run(name, arguments, allowed=allowed)

        if result.kind == "error":
            log_checkpoint(checkpoint_name, name, "error", error=RuntimeError(result.data.get("message", "Tool execution error")))
        else:
            log_checkpoint(checkpoint_name, name, "completed")
        return result.to_json()
    except Exception as exc:
        log_checkpoint(checkpoint_name, name, "error", error=exc)
        raise
