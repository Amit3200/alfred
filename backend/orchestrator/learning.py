"""Meta-learning loop analyzer to autonomously generate new playbooks from developer trajectories."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from backend.ai.base import Message
from backend.ai.registry import LLMRouter
from backend.models.config import AlfredConfig
from backend.models.task import Task
from backend.paths import playbooks_dir

logger = logging.getLogger(__name__)

from backend.orchestrator.prompts import META_LEARNING_PROMPT

def analyze_and_generate_playbook(
    task: Task,
    response_text: str,
    config: AlfredConfig,
    data_dir: str | None = None,
) -> str | None:
    """Analyze successful conversation turns and generate playbooks dynamically."""
    if not config.orchestrator.self_improvement:
        return None

    intent = (task.cleaned_intent or "").strip()
    if not intent or len(intent) < 5 or not response_text.strip():
        return None

    try:
        router = LLMRouter.from_config(config, data_dir=data_dir)
        provider = router.get()  # Get default configured provider
        model_name = config.ai.providers[config.ai.default_provider].model or ""
        
        messages = [
            Message(
                role="system",
                content=META_LEARNING_PROMPT.format(intent=intent, response_text=response_text)
            ),
            Message(
                role="user",
                content="Analyze query and respond with either a structured Markdown playbook or 'NONE'."
            )
        ]
        
        llm_response = provider.chat(messages, model=model_name or None)
        result = (llm_response.content or "").strip()
        
        if not result or result.upper() == "NONE":
            return None
            
        # Parse playbook name from YAML
        name = "custom_learned"
        for line in result.splitlines():
            if line.startswith("name:"):
                name = line.split(":", 1)[1].strip().strip('"\'')
                break
                
        # Clean name to be safe filename
        name_clean = "".join(c for c in name if c.isalnum() or c in ("_", "-")).lower()
        if not name_clean:
            name_clean = "custom_learned"

        data_dir_path = Path(data_dir) if data_dir else None
        if config.orchestrator.self_improvement_requires_review:
            from backend.orchestrator.playbook_pending import enqueue_pending_playbook

            pending_id = enqueue_pending_playbook(
                task=task,
                proposed_content=result,
                playbook_name=name_clean,
                data_dir=data_dir_path,
            )
            logger.info(
                "Queued self-learned playbook %s for review (pending_id=%s)",
                name_clean,
                pending_id,
            )
            return pending_id

        target_dir = playbooks_dir(data_dir_path)
        target_dir.mkdir(parents=True, exist_ok=True)

        target_file = target_dir / f"{name_clean}.md"
        target_file.write_text(result, encoding="utf-8")
        from backend.routing.playbook_store_registry import invalidate_playbook_store

        invalidate_playbook_store(data_dir_path)
        logger.info("Autonomously generated new playbook: %s", target_file)
        return str(target_file)
        
    except Exception as e:
        logger.exception("Failed in meta-learning analyzer loop")
        return None
