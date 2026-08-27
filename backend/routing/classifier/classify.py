"""Intent classification — AI when enabled, deterministic fallback always."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.models.config import AlfredConfig
from backend.models.task import Task
from backend.routing.create_target_precedence import should_route_create_to_jira
from backend.routing.entity_extractor import EntityBag, extract_entities
from backend.routing.html_slides_delivery import looks_like_html_slides_request
from backend.routing.jira.intent import (
    looks_like_jira_assign_request,
    looks_like_jira_create_request,
    looks_like_jira_transition_request,
)
from backend.routing.slack_board.intent import (
    looks_like_slack_board_create,
    looks_like_slack_board_update,
)


@dataclass(frozen=True)
class IntentClassification:
    intent_class: str
    target_system: str
    confidence: float
    entities: dict[str, Any] = field(default_factory=dict)
    ambiguous_with: tuple[str, ...] = ()
    strategy: str = "rules"


def classify_intent(
    task: Task,
    *,
    config: AlfredConfig,
    session_turns: tuple[str, ...] = (),
    session_metadata: dict[str, Any] | None = None,
    thread_context: str = "",
    entities: EntityBag | None = None,
    session: Any | None = None,
    data_dir: Any | None = None,
) -> IntentClassification:
    """Prompt router first; entity-direct and rules only when the model cannot decide."""
    bag = entities or extract_entities(task.cleaned_intent or "", task.raw_text or "", thread_context)
    direct = _entity_direct_read(task, config=config, entities=bag)
    if direct is not None:
        return direct
    if getattr(config.routing, "classifier_enabled", True):
        from backend.routing.classifier.hierarchical import classify_intent_hierarchical
        from backend.routing.classifier.query_context import gather_query_metadata

        metadata = gather_query_metadata(
            task,
            config=config,
            session=session,
            entities=bag,
            data_dir=data_dir,
        )
        llm = classify_intent_hierarchical(
            task,
            config=config,
            metadata=metadata,
            session_turns=session_turns,
        )
        if llm is not None and llm.confidence >= 0.55:
            return llm
    return classify_intent_rules(
        task,
        config=config,
        session_turns=session_turns,
        session_metadata=session_metadata,
        thread_context=thread_context,
        entities=bag,
        data_dir=data_dir,
    )


def _entity_payload(bag: EntityBag) -> dict[str, Any]:
    return {
        "issue_keys": list(bag.issue_keys),
        "spreadsheet_ids": list(bag.spreadsheet_ids),
        "document_ids": list(bag.document_ids),
    }


def _entity_direct_read(
    task: Task,
    *,
    config: AlfredConfig,
    entities: EntityBag,
) -> IntentClassification | None:
    """Skip the LLM when the message is essentially a Jira issue key lookup."""
    if not config.jira.enabled or not entities.issue_keys:
        return None
    text = f"{task.cleaned_intent}\n{task.raw_text}".strip()
    if len(text.split()) > 8:
        return None
    if looks_like_jira_create_request(task.cleaned_intent or text):
        return None
    if looks_like_jira_assign_request(text) or looks_like_jira_transition_request(text):
        return None
    if looks_like_html_slides_request(text):
        return None
    return IntentClassification(
        intent_class="jira.read.single",
        target_system="jira",
        confidence=0.95,
        entities={**_entity_payload(entities), "issue_key": entities.issue_keys[0]},
        strategy="entity_direct",
    )


def classify_intent_rules(
    task: Task,
    *,
    config: AlfredConfig,
    session_turns: tuple[str, ...] = (),
    session_metadata: dict[str, Any] | None = None,
    thread_context: str = "",
    entities: EntityBag | None = None,
    data_dir: Any = None,
) -> IntentClassification:
    text = f"{task.cleaned_intent}\n{task.raw_text}".strip()
    bag = entities or extract_entities(text, thread_context)
    entity_payload = _entity_payload(bag)

    from backend.routing.schedule_intent import looks_like_schedule_request, schedule_intent_class

    if looks_like_schedule_request(text):
        return IntentClassification(
            intent_class=schedule_intent_class(text),
            target_system="schedule",
            confidence=0.93,
            entities=entity_payload,
        )

    if looks_like_html_slides_request(text):
        return IntentClassification(
            intent_class="artifact.write.deck",
            target_system="artifact",
            confidence=0.92,
            entities=entity_payload,
        )

    jira_create = config.jira.enabled and (
        looks_like_jira_create_request(task.cleaned_intent or text)
        or should_route_create_to_jira(
            task.cleaned_intent or text,
            jira_enabled=True,
            session_turns=session_turns,
            session_metadata=session_metadata,
            thread_context=thread_context,
            channel_id=task.channel_id or "",
            data_dir=data_dir,
        )
    )
    if jira_create:
        return IntentClassification(
            intent_class="jira.write.create",
            target_system="jira",
            confidence=0.93,
            entities=entity_payload,
        )

    if bag.issue_keys and looks_like_jira_assign_request(text):
        return IntentClassification(
            intent_class="jira.write.assign",
            target_system="jira",
            confidence=0.9,
            entities={**entity_payload, "issue_key": bag.issue_keys[0]},
        )

    if bag.issue_keys and looks_like_jira_transition_request(text):
        return IntentClassification(
            intent_class="jira.write.transition",
            target_system="jira",
            confidence=0.88,
            entities={**entity_payload, "issue_key": bag.issue_keys[0]},
        )

    if bag.issue_keys and len(text.split()) <= 8:
        return IntentClassification(
            intent_class="jira.read.single",
            target_system="jira",
            confidence=0.9,
            entities={**entity_payload, "issue_key": bag.issue_keys[0]},
        )

    if looks_like_slack_board_update(task.cleaned_intent or text):
        return IntentClassification(
            intent_class="slack.board.write.update",
            target_system="slack_board",
            confidence=0.88,
            entities=entity_payload,
        )

    if looks_like_slack_board_create(task.cleaned_intent or text):
        return IntentClassification(
            intent_class="slack.board.write.create",
            target_system="slack_board",
            confidence=0.88,
            entities=entity_payload,
        )

    from backend.routing.tool_planner import looks_like_repo_doc_question

    if looks_like_repo_doc_question(task.cleaned_intent or text, source=task.source):
        return IntentClassification(
            intent_class="repo.docs.qa",
            target_system="repo",
            confidence=0.88,
            entities=entity_payload,
        )

    return IntentClassification(
        intent_class="unknown",
        target_system="",
        confidence=0.2,
        entities=entity_payload,
        strategy="rules",
    )
