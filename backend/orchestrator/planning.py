"""Task planning helper - manages plan generation, context injection, and checkbox updates."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from backend.ai.base import Message
from backend.ai.registry import LLMRouter
from backend.models.config import AlfredConfig
from backend.models.task import Task
from backend.paths import get_data_dir

logger = logging.getLogger(__name__)

from backend.orchestrator.prompts import PLANNING_PROMPT, UPDATE_PLAN_PROMPT

def plans_dir(data_dir: Path | None = None) -> Path:
    """Resolve directory for task plan storage."""
    base = get_data_dir(data_dir)
    return base / "plans"

def generate_initial_plan(
    task: Task,
    allowed_tools: list[str],
    config: AlfredConfig,
    data_dir: str | None = None,
) -> str | None:
    """Generate the initial execution plan checklist and save it to disk."""
    intent = (task.cleaned_intent or "").strip()
    if not intent:
        return None

    try:
        router = LLMRouter.from_config(config, data_dir=data_dir)
        provider = router.get()
        model_name = config.ai.providers[config.ai.default_provider].model or ""
        
        tools_str = "\n".join(f"- {name}" for name in allowed_tools)
        messages = [
            Message(
                role="system",
                content=PLANNING_PROMPT.format(intent=intent, tools=tools_str)
            ),
            Message(
                role="user",
                content="Create the initial task checklist plan."
            )
        ]
        
        from backend.observability.context import set_call_kind
        set_call_kind("planning")
        try:
            response = provider.chat(messages, model=model_name or None)
        finally:
            set_call_kind("chat")
        plan_content = (response.content or "").strip()
        if not plan_content:
            return None
            
        data_dir_path = Path(data_dir) if data_dir else None
        target_dir = plans_dir(data_dir_path)
        target_dir.mkdir(parents=True, exist_ok=True)
        
        plan_file = target_dir / f"plan_{task.id}.md"
        plan_file.write_text(plan_content, encoding="utf-8")
        logger.info("Generated initial plan for task %s: %s", task.id, plan_file)
        return plan_content
        
    except Exception:
        logger.exception("Failed to generate task plan")
        return None

def update_plan_progress(
    task_id: str,
    last_action: str,
    last_result: str,
    config: AlfredConfig,
    data_dir: str | None = None,
) -> str | None:
    """Update checkbox progress inside the task plan file based on the last execution step."""
    data_dir_path = Path(data_dir) if data_dir else None
    plan_file = plans_dir(data_dir_path) / f"plan_{task_id}.md"
    if not plan_file.is_file():
        return None

    try:
        current_plan = plan_file.read_text(encoding="utf-8")
        router = LLMRouter.from_config(config, data_dir=data_dir)
        provider = router.get()
        model_name = config.ai.providers[config.ai.default_provider].model or ""
        
        messages = [
            Message(
                role="system",
                content=UPDATE_PLAN_PROMPT.format(
                    current_plan=current_plan,
                    last_action=last_action,
                    last_result=last_result,
                )
            ),
            Message(
                role="user",
                content="Update checklist checkboxes."
            )
        ]
        
        from backend.observability.context import set_call_kind
        set_call_kind("planning")
        try:
            response = provider.chat(messages, model=model_name or None)
        finally:
            set_call_kind("chat")
        updated_content = (response.content or "").strip()
        
        # Strip any code block backticks if the LLM returned them
        if updated_content.startswith("```"):
            lines = updated_content.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            updated_content = "\n".join(lines).strip()
            
        if updated_content and "Task Plan" in updated_content:
            plan_file.write_text(updated_content, encoding="utf-8")
            logger.info("Updated task plan progress for task %s", task_id)
            return updated_content
            
        return current_plan
        
    except Exception:
        logger.exception("Failed to update task plan progress")
        return None
