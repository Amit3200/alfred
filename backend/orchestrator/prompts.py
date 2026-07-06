"""System prompts for Alfred Slack and CLI interactions."""

from __future__ import annotations
from backend.branding.display import branding_identity_line
from backend.models.config import AlfredConfig as ConfigModel
from backend.integrations.slack.users import format_user_id_legend


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.models.config import AlfredConfig

import yaml
from pathlib import Path

_yaml_path = Path(__file__).parent / "prompts.yaml"
try:
    _prompts = yaml.safe_load(_yaml_path.read_text(encoding="utf-8")) or {}
except Exception:
    _prompts = {}

ALFRED_IDENTITY = (_prompts.get("identity") or "You are Alfred — the company's AI assistant.").strip()
SLACK_FORMAT_RULES = (_prompts.get("slack_format_rules") or "").strip()
GITHUB_COMMENT_RULES = (_prompts.get("github_comment_rules") or "").strip()
HERMES_SYSTEM_INSTRUCTIONS = (_prompts.get("hermes_system_instructions") or "").strip()
META_LEARNING_PROMPT = (_prompts.get("meta_learning_prompt") or "").strip()
PLANNING_PROMPT = (_prompts.get("planning_prompt") or "").strip()
UPDATE_PLAN_PROMPT = (_prompts.get("update_plan_prompt") or "").strip()


def build_alfred_system_prompt(config: AlfredConfig | None = None, model_name: str | None = None) -> str:
    cfg = config or ConfigModel()
    identity = branding_identity_line(cfg.branding)
    
    prompt = f"{identity}\n\n{ALFRED_IDENTITY}\n\n{SLACK_FORMAT_RULES}"
    
    if model_name:
        model_lower = model_name.lower()
        if "kimi" in model_lower or "moonshot" in model_lower:
            prompt += """\n\n## Moonshot/Kimi Optimization
- You are running on Moonshot Kimi. Be extremely concise.
- If the Slack context size is large, prioritize a dense summary over long listings to prevent context errors.
- Do not output thinking blocks or metadata labels (e.g., 'Lead line', 'Body') unless asked."""
        elif "claude" in model_lower or "anthropic" in model_lower:
            prompt += """\n\n## Anthropic/Claude Optimization
- You are running on Anthropic Claude.
- Strictly adhere to Slack bold (*word*) instead of GFM bold (**word**).
- Structure responses clearly, and do not repeat the instruction guidelines in your output."""
            
    return prompt


ALFRED_SYSTEM_PROMPT = build_alfred_system_prompt()


def build_slack_user_message(
    task_intent: str,
    slack_context: str | None,
    *,
    history_window_label: str = "",
    user_names: dict[str, str] | None = None,
) -> str:
    """Wrap user intent + Slack context for a single model turn."""
    if not slack_context:
        return task_intent
    pass

    window_note = history_window_label or "the fetched window"
    header = (
        "[Slack context — facts only; do not invent details]\n"
        f"Readable window: {window_note}. "
        "If the answer is not in the messages below, tell the user your context window "
        "is limited and the query may be outside that range — do not guess."
    )
    legend = format_user_id_legend(user_names or {})
    parts = [task_intent, header]
    if legend:
        parts.append(legend)
    parts.append(slack_context)
    return "\n\n".join(parts)
