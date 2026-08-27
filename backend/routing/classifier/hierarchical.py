"""Two-stage prompt router: pick tool parent, then the best matching function."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from backend.ai.base import Message
from backend.models.config import AlfredConfig
from backend.models.task import Task
from backend.routing.capabilities import capability_for_tool, tools_for_capability
from backend.routing.classifier.classify import IntentClassification
from backend.routing.classifier.intent_classes import canonical_intent_class
from backend.routing.classifier.parents import PARENT_BY_ID, ToolParent, enabled_parents
from backend.routing.classifier.query_context import QueryMetadata
from backend.tools.catalog_formatter import get_tool_description

logger = logging.getLogger(__name__)

_JSON_RE = re.compile(r"\{.*\}", re.S)

_AMBIGUOUS_CREATE = ("jira.write.create", "slack.board.write.create")


def classify_intent_hierarchical(
    task: Task,
    *,
    config: AlfredConfig,
    metadata: QueryMetadata,
    session_turns: tuple[str, ...] = (),
) -> IntentClassification | None:
    """Parent catalog → function catalog. Returns None if the model is unavailable or invalid."""
    parents = enabled_parents(config, slack_board_linked=metadata.slack_board_linked)
    if not parents:
        return None
    try:
        from backend.ai.registry import LLMRouter

        provider = LLMRouter.from_config(config).for_task("skill_matching")
        if hasattr(provider, "is_available") and not provider.is_available():
            return None
    except Exception:
        return None

    parent, parent_payload = _select_parent(
        provider,
        task,
        metadata=metadata,
        parents=parents,
        session_turns=session_turns,
    )
    if parent is None:
        return None
    if parent.id == "conversational":
        ambiguous = _ambiguous_systems(parent_payload, parents)
        return IntentClassification(
            intent_class="conversational",
            target_system="",
            confidence=_confidence(parent_payload, default=0.8),
            entities=metadata.entities,
            ambiguous_with=ambiguous,
            strategy="llm_hierarchical",
        )
    return _select_function(
        provider,
        task,
        metadata=metadata,
        parent=parent,
        session_turns=session_turns,
    )


def _select_parent(
    provider: Any,
    task: Task,
    *,
    metadata: QueryMetadata,
    parents: list[ToolParent],
    session_turns: tuple[str, ...],
) -> tuple[ToolParent | None, dict[str, Any]]:
    lines = [
        "You route user requests to exactly one TOOL PARENT (integration family).",
        "Do not pick a function yet. Pick the parent only.",
        "",
        "How to choose:",
        "1. Read query metadata (channel, Slack List binding, Jira project, entities, session).",
        "2. Read the user text and recent turns.",
        "3. Pick the parent whose description best matches the request semantically.",
        "",
        "Hard rules:",
        "- If the user names Jira, a Jira project, or an issue key (TECH-12 or TECH 12), parent is jira.",
        "- If they ask to update/modify/edit an existing issue, parent is jira (jira_update_issue), "
        "not a Slack List lookup.",
        "- If channel_prefers_jira_creates is true and they ask to create a task/ticket, "
        "parent is jira unless they named Slack List / slack board.",
        "- If a Slack List is linked to this channel and they say create/update a task/board "
        "without naming Jira, AND channel_prefers_jira_creates is false, parent is slack_board.",
        "- If both Jira and a Slack List could apply and the user did not specify, "
        'parent is conversational and set ambiguous_with to ["jira","slack_board"].',
        "- Docs/runbooks → repo_docs. Public internet → web. HTML slides → artifact.",
        "- Greetings, chit-chat, or unclear asks → conversational (ambiguous_with empty).",
        "",
        "## Query metadata",
        metadata.prompt_block(),
        "",
        "## Recent turns",
        "\n".join(session_turns[-4:]) or "(none)",
        "",
        "## User",
        (task.cleaned_intent or task.raw_text or "").strip(),
        "",
        "## Tool parents (only these ids are valid)",
    ]
    parent_ids = {p.id for p in parents}
    for parent in parents:
        lines.append(f"- `{parent.id}`: {parent.description}{_parent_status(parent, metadata)}")
    lines.extend(
        [
            "",
            "Return JSON only: "
            '{"parent":"<id>","confidence":0.0,"reason":"<short>",'
            '"ambiguous_with":[]}',
        ]
    )
    payload = _chat_json(provider, "\n".join(lines))
    if not payload:
        return None, {}
    parent_id = str(payload.get("parent") or "").strip()
    chosen = PARENT_BY_ID.get(parent_id)
    if chosen is None or chosen.id not in parent_ids:
        return None, payload
    return chosen, payload


def _select_function(
    provider: Any,
    task: Task,
    *,
    metadata: QueryMetadata,
    parent: ToolParent,
    session_turns: tuple[str, ...],
) -> IntentClassification | None:
    catalog = _function_catalog(parent)
    if not catalog:
        return None
    lines = [
        f"The tool parent `{parent.id}` was already chosen.",
        "Pick the single best FUNCTION for this request.",
        "Match the user text contextually and semantically to function descriptions.",
        "Then report the capability that owns that function.",
        "Hard rules:",
        "- Update/modify/edit + issue key (TECH-363 or TECH 363) → jira_update_issue, never get_jira_issue.",
        "- Never invent summary/description as `<to be provided by user>` or similar placeholders; "
        "infer from the Slack thread.",
        "",
        "## Query metadata",
        metadata.prompt_block(),
        "",
        "## Recent turns",
        "\n".join(session_turns[-4:]) or "(none)",
        "",
        "## User",
        (task.cleaned_intent or task.raw_text or "").strip(),
        "",
        f"## Functions of `{parent.id}`",
        catalog,
        "",
        "Return JSON only: "
        '{"tool":"<function name>","intent_class":"<capability id>",'
        '"confidence":0.0,"reason":"<short>"}',
    ]
    payload = _chat_json(provider, "\n".join(lines))
    if not payload:
        return None

    tool_name = str(payload.get("tool") or "").strip()
    intent_class = ""
    if tool_name:
        intent_class = capability_for_tool(tool_name, candidates=parent.capabilities)
    if not intent_class:
        raw = str(payload.get("intent_class") or "").strip()
        mapped = canonical_intent_class(raw)
        if mapped != "unknown" and mapped in parent.capabilities:
            intent_class = mapped
        elif raw in parent.capabilities:
            intent_class = raw
    if not intent_class or intent_class not in parent.capabilities:
        return None

    target = parent.id if parent.id != "repo_docs" else "repo"
    return IntentClassification(
        intent_class=intent_class,
        target_system=target,
        confidence=_confidence(payload, default=0.75),
        entities=metadata.entities,
        strategy="llm_hierarchical",
    )


def _function_catalog(parent: ToolParent) -> str:
    blocks: list[str] = []
    seen_tools: set[str] = set()
    for cap in parent.capabilities:
        tools = tools_for_capability(cap)
        if not tools:
            continue
        lines = [f"### Capability `{cap}`"]
        for name in tools:
            if name in seen_tools:
                continue
            seen_tools.add(name)
            desc = get_tool_description(name) or name
            lines.append(f"- `{name}` — {desc}")
        if len(lines) > 1:
            blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _parent_status(parent: ToolParent, metadata: QueryMetadata) -> str:
    if parent.id == "jira":
        project = metadata.jira_default_project or "none"
        return f" [enabled, default_project={project}]"
    if parent.id == "slack_board":
        if metadata.slack_board_linked:
            name = metadata.slack_board_name or "?"
            list_id = metadata.slack_board_list_id or "?"
            return f" [THIS CHANNEL: linked list name={name} list_id={list_id}]"
        return " [THIS CHANNEL: no Slack List linked]"
    if parent.id == "slack_read":
        channel = metadata.channel_id or "none"
        return f" [channel_id={channel}]"
    return ""


def _ambiguous_systems(payload: dict[str, Any], parents: list[ToolParent]) -> tuple[str, ...]:
    parent_ids = {p.id for p in parents}
    raw = payload.get("ambiguous_with") or []
    if not isinstance(raw, list):
        return ()
    labels = {str(item).strip().lower() for item in raw if str(item).strip()}
    if "jira" in labels and "slack_board" in labels:
        if "jira" in parent_ids and "slack_board" in parent_ids:
            return _AMBIGUOUS_CREATE
    return ()


def _confidence(payload: dict[str, Any], *, default: float) -> float:
    try:
        value = float(payload.get("confidence") or default)
    except (TypeError, ValueError):
        value = default
    return max(0.0, min(value, 1.0))


def _chat_json(provider: Any, prompt: str) -> dict[str, Any] | None:
    try:
        response = provider.chat([Message(role="user", content=prompt)], max_tokens=256)
        content = (response.content or "").strip()
        match = _JSON_RE.search(content)
        if not match:
            return None
        payload = json.loads(match.group(0))
        return payload if isinstance(payload, dict) else None
    except Exception:
        logger.debug("Hierarchical classifier LLM call failed", exc_info=True)
        return None
