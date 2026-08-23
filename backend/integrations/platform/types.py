"""Shared types for inbound connectors (Periskope, and later others)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

EntityKind = Literal["ticket", "task", "message", "chat"]
EntityAction = Literal["upsert", "close", "ignore"]
ReplicaTarget = Literal["slack_board", "jira"]


@dataclass
class ExternalEntity:
    """Normalized work item from any connector, ready for Slack List / JIRA."""

    connector_id: str
    kind: EntityKind
    external_id: str
    title: str
    description: str = ""
    status: str = ""
    priority: str = "Medium"
    assignee_hint: str = ""
    labels: list[str] = field(default_factory=list)
    chat_id: str = ""
    chat_name: str = ""
    source_url: str = ""
    action: EntityAction = "upsert"
    extra: dict[str, Any] = field(default_factory=dict)

    def mapping_key(self) -> str:
        return f"{self.connector_id}:{self.kind}:{self.external_id}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "connector_id": self.connector_id,
            "kind": self.kind,
            "external_id": self.external_id,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "priority": self.priority,
            "assignee_hint": self.assignee_hint,
            "labels": list(self.labels),
            "chat_id": self.chat_id,
            "chat_name": self.chat_name,
            "source_url": self.source_url,
            "action": self.action,
        }


@dataclass
class ConnectorEvent:
    connector_id: str
    event_type: str
    entity: ExternalEntity | None = None
    needs_enrich: bool = False
    raw: dict[str, Any] = field(default_factory=dict)
