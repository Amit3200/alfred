"""Connector contract — ingest + normalize; Alfred owns Slack/JIRA writes."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from backend.integrations.platform.types import ConnectorEvent, ExternalEntity, ReplicaTarget
from backend.models.config import AlfredConfig


class Connector(ABC):
    id: str
    display_name: str

    def settings(self, config: AlfredConfig) -> Any:
        connectors = getattr(config, "connectors", None)
        return getattr(connectors, self.id, None) if connectors is not None else None

    def enabled(self, config: AlfredConfig) -> bool:
        instance = self.settings(config)
        return bool(instance and getattr(instance, "enabled", False))

    def webhook_secret(self, config: AlfredConfig) -> str:
        instance = self.settings(config)
        return str(getattr(instance, "webhook_secret", "") or "").strip() if instance else ""

    def replica_targets(self, config: AlfredConfig) -> tuple[ReplicaTarget, ...]:
        instance = self.settings(config)
        target = str(getattr(instance, "ticket_create_target", "slack_board") or "slack_board")
        if target == "both":
            return ("slack_board", "jira")
        if target == "jira":
            return ("jira",)
        return ("slack_board",)

    def accepts(self, config: AlfredConfig, entity: ExternalEntity) -> bool:
        return True

    @abstractmethod
    def verify_webhook(self, *, headers: dict[str, str], body: bytes, secret: str) -> bool: ...

    @abstractmethod
    def parse_webhook(self, *, headers: dict[str, str], body: bytes) -> list[ConnectorEvent]: ...

    def enrich(self, config: AlfredConfig, entity: ExternalEntity) -> ExternalEntity:
        return entity

    def health_check(self, config: AlfredConfig) -> dict[str, Any]:
        if not self.enabled(config):
            return {"ok": False, "skipped": True, "message": f"{self.display_name} disabled"}
        return {"ok": False, "message": "Health check not implemented"}

    def list_chats(self, config: AlfredConfig) -> list[dict[str, Any]]:
        raise NotImplementedError(f"{self.id} does not list chats")

    def list_tickets(self, config: AlfredConfig, *, limit: int = 50) -> list[ExternalEntity]:
        raise NotImplementedError(f"{self.id} does not list tickets")

    def list_tasks(self, config: AlfredConfig, *, limit: int = 50) -> list[ExternalEntity]:
        raise NotImplementedError(f"{self.id} does not list tasks")

    def list_messages(
        self,
        config: AlfredConfig,
        *,
        chat_id: str = "",
        start_time: str = "",
        end_time: str = "",
        limit: int = 100,
        intent: str = "",
    ) -> list[dict[str, Any]]:
        raise NotImplementedError(f"{self.id} does not list messages")
