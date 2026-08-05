"""Build scoped context blocks per turn."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.models.config import AlfredConfig
from backend.models.task import Task
from backend.routing.entity_extractor import EntityBag, extract_entities
from backend.routing.tool_plan_types import ToolPlan


@dataclass
class ContextEnvelope:
    """Scoped facts for a single task turn."""

    entities: EntityBag
    tool_plan: ToolPlan | None = None
    blocks: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


def build_context_envelope(
    config: AlfredConfig,
    task: Task,
    *,
    tool_plan: ToolPlan | None = None,
    slack_context: str | None = None,
    jira_context: str = "",
    google_context: str = "",
    git_context: str = "",
    repo_context: str = "",
    pr_context: str = "",
) -> ContextEnvelope:
    """Assemble only context slices relevant to this turn."""
    entities = extract_entities(
        task.cleaned_intent,
        task.raw_text,
        slack_context or "",
    )

    blocks: dict[str, str] = {}
    if repo_context.strip():
        blocks["repo"] = repo_context.strip()
    if git_context.strip():
        blocks["git"] = git_context.strip()

    intent_class = (tool_plan.intent_class if tool_plan else "") or ""
    jira_domains = intent_class.startswith("jira") or bool(entities.issue_keys)
    google_domains = intent_class.startswith("google") or bool(
        entities.spreadsheet_ids or entities.document_ids
    )

    if jira_domains and jira_context.strip():
        blocks["jira"] = jira_context.strip()
    if google_domains and google_context.strip():
        blocks["google"] = google_context.strip()
    if pr_context.strip():
        blocks["pr"] = pr_context.strip()

    if entities.issue_keys:
        blocks["entities"] = f"Detected JIRA keys: {', '.join(entities.issue_keys)}"
    elif entities.spreadsheet_ids:
        blocks["entities"] = f"Detected spreadsheet IDs: {', '.join(entities.spreadsheet_ids)}"
    elif entities.document_ids:
        blocks["entities"] = f"Detected document IDs: {', '.join(entities.document_ids)}"

    return ContextEnvelope(
        entities=entities,
        tool_plan=tool_plan,
        blocks=blocks,
        metadata={"intent_class": intent_class},
    )


def format_context_envelope(envelope: ContextEnvelope) -> str:
    parts: list[str] = []
    if envelope.tool_plan and envelope.tool_plan.goal:
        parts.append(f"## Goal\n{envelope.tool_plan.goal}")
    for key in ("entities", "jira", "google", "git", "repo", "pr"):
        if block := envelope.blocks.get(key):
            parts.append(block)
    return "\n\n".join(parts)
