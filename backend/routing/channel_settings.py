"""Per-channel Slack board settings: persona prompt and docs-search toggle."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.db.slack_workflows_db import db_get_board_binding_for_channel
from backend.models.config import AlfredConfig
from backend.models.task import Task


def channel_board_settings(data_dir: Path | None, channel_id: str) -> dict[str, Any]:
    cid = (channel_id or "").strip()
    if not cid or data_dir is None:
        return {"persona_prompt": "", "docs_search_enabled": False}
    binding = db_get_board_binding_for_channel(data_dir, cid)
    if not binding:
        return {"persona_prompt": "", "docs_search_enabled": False}
    return {
        "persona_prompt": str(binding.get("persona_prompt") or "").strip(),
        "docs_search_enabled": bool(binding.get("docs_search_enabled")),
    }


def channel_persona_prompt(data_dir: Path | None, channel_id: str) -> str:
    return str(channel_board_settings(data_dir, channel_id).get("persona_prompt") or "")


def channel_persona_system_block(data_dir: Path | None, channel_id: str) -> str:
    prompt = channel_persona_prompt(data_dir, channel_id)
    if not prompt:
        return ""
    return f"## Channel persona\nFollow this channel-specific instruction first:\n{prompt}"


def channel_docs_search_enabled(data_dir: Path | None, channel_id: str) -> bool:
    return bool(channel_board_settings(data_dir, channel_id).get("docs_search_enabled"))


def is_channel_write_or_admin_intent(text: str) -> bool:
    """True when the message should stay on board/JIRA/connector/schedule paths."""
    from backend.routing.connector_intent import looks_like_connector_request
    from backend.routing.html_slides_delivery import looks_like_html_slides_request
    from backend.routing.schedule_intent import looks_like_schedule_request
    from backend.routing.slack_board.intent import (
        looks_like_setup_board_command,
        looks_like_slack_board_config_question,
        looks_like_slack_board_request,
        looks_like_slack_board_update,
    )

    raw = (text or "").strip()
    if not raw:
        return False
    if looks_like_slack_board_config_question(raw):
        return True
    if looks_like_setup_board_command(raw):
        return True
    if looks_like_slack_board_request(raw):
        return True
    if looks_like_slack_board_update(raw):
        return True
    if looks_like_html_slides_request(raw):
        return True
    if looks_like_schedule_request(raw):
        return True
    if looks_like_connector_request(raw):
        return True
    return False


def should_force_channel_docs_search(
    task: Task,
    data_dir: Path | None,
    *,
    config: AlfredConfig | None = None,
) -> bool:
    """True when this Slack turn should answer from indexed docs."""
    if task.source != "slack" or not task.channel_id:
        return False
    if config is not None and not config.repo_knowledge.enabled:
        return False
    if not channel_docs_search_enabled(data_dir, task.channel_id):
        return False
    text = (task.cleaned_intent or task.raw_text or "").strip()
    if not text:
        return False
    if is_channel_write_or_admin_intent(text):
        return False
    return True
