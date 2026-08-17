"""Single turn resolver — intent + capability + tools for this request."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.models.config import AlfredConfig
from backend.models.task import Task
from backend.routing.capabilities import tools_for_capability
from backend.routing.classifier.classify import IntentClassification, classify_intent
from backend.routing.classifier.intent_classes import (
    INTENT_TO_CAPABILITY,
    INTENT_TO_SKILL,
    INTENT_TO_TOOLS,
    canonical_intent_class,
)
from backend.routing.entity_extractor import extract_entities


@dataclass(frozen=True)
class TurnPlan:
    intent_class: str
    capability: str
    target_system: str
    tools: list[str]
    route: str  # direct | worker | conversational
    skill_name: str
    confidence: float
    entities: dict[str, Any] = field(default_factory=dict)
    ambiguous_with: tuple[str, ...] = ()
    strategy: str = "rules"

    @property
    def prefers_jira(self) -> bool:
        return self.target_system == "jira" or self.intent_class.startswith("jira.")

    @property
    def prefers_slack_board(self) -> bool:
        return self.target_system == "slack_board" or self.intent_class.startswith("slack.board.")

    def to_metadata(self) -> dict[str, Any]:
        return {
            "intent_class": self.intent_class,
            "capability": self.capability,
            "target_system": self.target_system,
            "tools": list(self.tools),
            "route": self.route,
            "skill_name": self.skill_name,
            "confidence": self.confidence,
            "strategy": self.strategy,
        }


def resolve_turn(
    task: Task,
    *,
    config: AlfredConfig,
    session: Any | None = None,
    thread_context: str = "",
) -> TurnPlan:
    session_turns: tuple[str, ...] = ()
    session_metadata: dict[str, Any] = {}
    if session is not None:
        session_metadata = dict(getattr(session, "metadata", None) or {})
        turns = getattr(session, "turns", None) or []
        session_turns = tuple(
            str(turn.content) for turn in turns[-8:] if str(getattr(turn, "content", "") or "").strip()
        )
    bag = extract_entities(task.cleaned_intent or "", task.raw_text or "", thread_context)
    classification = classify_intent(
        task,
        config=config,
        session_turns=session_turns,
        session_metadata=session_metadata,
        thread_context=thread_context,
        entities=bag,
        session=session,
        data_dir=getattr(config, "data_dir", None),
    )
    return turn_plan_from_classification(classification, config=config)


def turn_plan_from_classification(
    classification: IntentClassification,
    *,
    config: AlfredConfig,
) -> TurnPlan:
    intent_class = canonical_intent_class(classification.intent_class)
    if intent_class == "unknown" and classification.intent_class in INTENT_TO_CAPABILITY:
        intent_class = classification.intent_class
    capability = INTENT_TO_CAPABILITY.get(intent_class, "")
    data_dir = getattr(config, "data_dir", None)
    tools = tools_for_capability(capability, data_dir=data_dir) if capability else []
    if not tools:
        tools = list(INTENT_TO_TOOLS.get(intent_class, ()))
    skill_name = INTENT_TO_SKILL.get(intent_class, "")
    route = _choose_route(classification, tools)
    return TurnPlan(
        intent_class=intent_class,
        capability=capability,
        target_system=classification.target_system,
        tools=tools,
        route=route,
        skill_name=skill_name,
        confidence=classification.confidence,
        entities=classification.entities,
        ambiguous_with=classification.ambiguous_with,
        strategy=classification.strategy,
    )


def _choose_route(classification: IntentClassification, tools: list[str]) -> str:
    if classification.ambiguous_with:
        return "conversational"
    intent_class = canonical_intent_class(classification.intent_class)
    if intent_class in ("unknown", "conversational"):
        return "conversational"
    if intent_class in ("jira.write.create", "artifact.write.deck", "repo.docs.qa"):
        return "worker"
    if intent_class in ("jira.read.single", "slack.board.write.update"):
        return "direct"
    if classification.confidence >= 0.9 and len(tools) == 1:
        return "direct"
    return "worker"
