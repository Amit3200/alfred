"""Unified agent loop — ReAct and autonomous (Hermes) modes."""

from __future__ import annotations

import logging
from typing import Any, Literal

from backend.ai.base import LLMProvider, LLMResponse, Message, ToolCall
from backend.agent.execute import execute_tool
from backend.agent.synthesis import synthesize_final_answer
from backend.observability.checkpoint import current_data_dir, current_task_id, log_checkpoint
from backend.orchestrator.prompts import AUTONOMOUS_SYSTEM_INSTRUCTIONS, GROUNDING_CONTRACT
from backend.orchestrator.task_cancel import raise_if_cancelled
from backend.routing.git.direct import parse_text_tool_call, strip_text_tool_markup
from backend.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

AgentMode = Literal["react", "autonomous"]
DEFAULT_MAX_ITERATIONS = 20


def _mode_label(mode: AgentMode) -> str:
    return "autonomous" if mode == "autonomous" else "react"


def _inject_system_directives(messages: list[Message], *, mode: AgentMode) -> list[Message]:
    conversation = list(messages)
    extra_blocks = [GROUNDING_CONTRACT.strip()]
    if mode == "autonomous":
        extra_blocks.append(AUTONOMOUS_SYSTEM_INSTRUCTIONS.strip())

    suffix = "\n\n".join(block for block in extra_blocks if block)
    if not suffix:
        return conversation

    if conversation and conversation[0].role == "system":
        conversation[0] = Message(
            role="system",
            content=f"{conversation[0].content.rstrip()}\n\n{suffix}",
        )
    else:
        conversation.insert(0, Message(role="system", content=suffix))
    return conversation


def _inject_plan_checklist(
    conversation: list[Message],
    plan_content: str | None,
    *,
    mode: AgentMode,
) -> None:
    if not plan_content:
        return
    plan_block = f"## Task Plan Checklist\n{plan_content}"
    prefix = ""
    if mode == "autonomous" and AUTONOMOUS_SYSTEM_INSTRUCTIONS.strip():
        prefix = f"{AUTONOMOUS_SYSTEM_INSTRUCTIONS.strip()}\n\n"
    for idx, msg in enumerate(conversation):
        if msg.role == "system" and "## Task Plan Checklist" in msg.content:
            conversation[idx] = Message(role="system", content=f"{prefix}{plan_block}")
            return
    conversation.insert(1, Message(role="system", content=plan_block))


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


def _update_plan_progress(task_id: str, data_dir: Any, session: Any, tool_name: str, args: dict, observation: str) -> None:
    try:
        from backend.config_manager import ConfigManager
        from backend.orchestrator.planning import update_plan_progress

        config, _ = ConfigManager(data_dir).load_merged()
        last_action = f"Called tool {tool_name} with args {args}"
        update_plan_progress(task_id, last_action, observation, config, data_dir)
    except Exception:
        logger.exception("Failed to update plan progress in agent loop")


def _is_confirmation_block(observation: str) -> bool:
    return "requires explicit approval" in (observation or "").lower()


def _remember_board_creates_from_calls(session: Any, tool_calls: list[ToolCall]) -> None:
    from backend.routing.slack_board.pending import remember_pending_board_create

    for tool_call in tool_calls:
        if tool_call.name != "slack_board_create_task":
            continue
        args = tool_call.arguments or {}
        remember_pending_board_create(
            session,
            title=str(args.get("title") or ""),
            severity=str(args.get("severity") or ""),
            assignee_user_id=str(args.get("assignee_user_id") or args.get("assignee") or ""),
        )


def run_agent(
    provider: LLMProvider,
    messages: list[Message],
    registry: ToolRegistry,
    allowed_tools: list[str],
    *,
    mode: AgentMode = "react",
    model: str | None = None,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    session: Any | None = None,
    git: Any | None = None,
    max_tokens: int | None = None,
) -> str:
    """Run tool-augmented chat until the model returns text or limits are hit."""
    tool_schemas = registry.get_schemas(allowed_tools)
    if not tool_schemas:
        raise RuntimeError("No tools available for the matched skill.")

    conversation = _inject_system_directives(messages, mode=mode)
    task_id = current_task_id.get()
    data_dir = current_data_dir.get()
    session_key = getattr(session, "session_key", None) if session is not None else None
    runner_label = _mode_label(mode)

    def get_plan_context() -> str | None:
        if task_id:
            from backend.orchestrator.planning import resolve_plan_for_task

            return resolve_plan_for_task(task_id, session=session, data_dir=data_dir)
        return None

    log_checkpoint(f"{runner_label}_loop_start", runner_label, "started")

    for iteration in range(max_iterations):
        raise_if_cancelled(data_dir, task_id)
        logger.debug("%s loop iteration %d", runner_label, iteration + 1)

        _inject_plan_checklist(conversation, get_plan_context(), mode=mode)

        iter_checkpoint = f"{runner_label}_loop_iteration"
        log_checkpoint(iter_checkpoint, f"iteration_{iteration + 1}", "started")

        try:
            response = provider.chat(
                conversation,
                tools=tool_schemas,
                model=model,
                max_tokens=max_tokens,
            )
        except Exception as exc:
            log_checkpoint(iter_checkpoint, f"iteration_{iteration + 1}", "error", error=exc)
            raise

        if response.tool_calls:
            conversation.append(_assistant_tool_message(response))
            confirmation_observation = ""
            for tool_call in response.tool_calls:
                if confirmation_observation:
                    if tool_call.name == "slack_board_create_task":
                        _remember_board_creates_from_calls(session, [tool_call])
                    if tool_call.name != "slack_fetch_thread":
                        conversation.append(
                            Message(
                                role="tool",
                                content="Skipped: waiting for write approval.",
                                tool_call_id=tool_call.id,
                                name=tool_call.name,
                            )
                        )
                        continue
                observation = execute_tool(
                    registry,
                    tool_call.name,
                    tool_call.arguments,
                    allowed=allowed_tools,
                    session=session,
                    git=git,
                    task_id=task_id,
                    session_key=session_key,
                )
                conversation.append(
                    Message(
                        role="tool",
                        content=observation,
                        tool_call_id=tool_call.id,
                        name=tool_call.name,
                    )
                )
                if task_id and data_dir:
                    _update_plan_progress(
                        task_id,
                        data_dir,
                        session,
                        tool_call.name,
                        tool_call.arguments,
                        observation,
                    )
                if _is_confirmation_block(observation):
                    confirmation_observation = observation
                    _remember_board_creates_from_calls(session, [tool_call])
            if confirmation_observation:
                from backend.governance.confirmation import confirmation_required_board_batch_message
                from backend.routing.slack_board.pending import get_pending_board_creates

                pending = get_pending_board_creates(session)
                if len(pending) >= 2:
                    log_checkpoint(iter_checkpoint, f"iteration_{iteration + 1}_confirmation", "completed")
                    return confirmation_required_board_batch_message(
                        [item["title"] for item in pending]
                    )
                log_checkpoint(iter_checkpoint, f"iteration_{iteration + 1}_confirmation", "completed")
                return confirmation_observation
            log_checkpoint(iter_checkpoint, f"iteration_{iteration + 1}_tool_called", "completed")
            continue

        content = (response.content or "").strip()
        if content:
            parsed = parse_text_tool_call(content)
            if parsed:
                name, arguments = parsed
                if name in allowed_tools:
                    tool_id = f"{runner_label}_text_call_{iteration + 1}"
                    logger.info("%s executing text-emitted tool call: %s", runner_label, name)
                    summary = strip_text_tool_markup(content) or f"Calling {name}..."
                    conversation.append(
                        Message(
                            role="assistant",
                            content=summary,
                            tool_calls=[ToolCall(id=tool_id, name=name, arguments=arguments)],
                        )
                    )
                    observation = execute_tool(
                        registry,
                        name,
                        arguments,
                        allowed=allowed_tools,
                        session=session,
                        git=git,
                        task_id=task_id,
                        session_key=session_key,
                    )
                    conversation.append(
                        Message(
                            role="tool",
                            content=observation,
                            tool_call_id=tool_id,
                            name=name,
                        )
                    )
                    if task_id and data_dir:
                        _update_plan_progress(task_id, data_dir, session, name, arguments, observation)
                    if _is_confirmation_block(observation):
                        log_checkpoint(iter_checkpoint, f"iteration_{iteration + 1}_confirmation", "completed")
                        return observation
                    log_checkpoint(iter_checkpoint, f"iteration_{iteration + 1}_text_tool_called", "completed")
                    continue

            log_checkpoint(iter_checkpoint, f"iteration_{iteration + 1}_final_answer", "completed")
            return content

        fallback = (
            "I ran the available tools but could not form a final answer. "
            "Try rephrasing or check integration settings."
        )
        log_checkpoint(iter_checkpoint, f"iteration_{iteration + 1}_no_response", "completed")
        return fallback

    synthesized = synthesize_final_answer(provider, conversation, model=model)
    if synthesized:
        log_checkpoint(f"{runner_label}_loop_synthesis", runner_label, "completed")
        return synthesized

    exhausted = (
        "I ran out of investigation steps before I could finish. "
        "Try a narrower question or split the request into smaller steps."
    )
    log_checkpoint(f"{runner_label}_loop_exhausted", runner_label, "completed")
    return exhausted
