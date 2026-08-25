"""Periskope connector — WhatsApp tickets/tasks/messages into Alfred."""

from __future__ import annotations

import json
import logging
from typing import Any

from backend.integrations.periskope.api import PeriskopeApiClient, PeriskopeApiError
from backend.integrations.periskope.normalize import (
    CONNECTOR_ID,
    entity_from_task,
    entity_from_ticket,
    parse_webhook_body,
)
from backend.integrations.platform.connector import Connector
from backend.integrations.platform.hmac import verify_hmac_sha256
from backend.integrations.platform.types import ConnectorEvent, ExternalEntity
from backend.models.config import AlfredConfig

logger = logging.getLogger(__name__)

_ALLOW_ALL_CHATS = frozenset({"*", "all"})


def _allowed_chat_ids(config: AlfredConfig) -> set[str]:
    """WhatsApp chat allowlist for poll/list. Empty / * / all means every chat."""
    settings = getattr(getattr(config, "connectors", None), "periskope", None)
    raw = getattr(settings, "allowed_chat_ids", None) or []
    if isinstance(raw, str):
        raw = [part.strip() for part in raw.split(",")]
    values = {str(item).strip() for item in raw if str(item).strip()}
    if not values or values & _ALLOW_ALL_CHATS:
        return set()
    return values


def _replication_enabled(config: AlfredConfig, entity: ExternalEntity) -> bool:
    settings = getattr(getattr(config, "connectors", None), "periskope", None)
    if entity.kind == "ticket" and not bool(getattr(settings, "replicate_tickets", True)):
        return False
    if entity.kind == "task" and not bool(getattr(settings, "replicate_tasks", True)):
        return False
    return True


def _allow_entity(
    config: AlfredConfig,
    entity: ExternalEntity,
    *,
    enforce_chat_allowlist: bool = True,
) -> bool:
    if not _replication_enabled(config, entity):
        return False
    allowed = _allowed_chat_ids(config)
    if enforce_chat_allowlist and allowed and entity.chat_id and entity.chat_id not in allowed:
        return False
    return True


def _normalize_message(message: dict[str, Any], *, chat_id: str = "") -> dict[str, Any]:
    sender = (
        message.get("sender_name")
        or message.get("performed_by")
        or message.get("sender_phone")
        or message.get("author")
        or message.get("from")
        or ""
    )
    ident = message.get("id") if isinstance(message.get("id"), dict) else {}
    return {
        "message_id": str(message.get("message_id") or ident.get("id") or "").strip(),
        "chat_id": chat_id or str(message.get("chat_id") or "").strip(),
        "sender_name": str(sender or "").strip(),
        "body": str(message.get("body") or "")[:800],
        "timestamp": str(message.get("timestamp") or "").strip(),
        "from_me": bool(message.get("from_me")),
    }


class PeriskopeConnector(Connector):
    id = CONNECTOR_ID
    display_name = "Periskope"

    def verify_webhook(self, *, headers: dict[str, str], body: bytes, secret: str) -> bool:
        signature = headers.get("x-periskope-signature") or headers.get("X-Periskope-Signature") or ""
        payload: dict[str, Any] | None = None
        try:
            parsed = json.loads(body or b"{}")
            if isinstance(parsed, dict):
                payload = parsed
        except json.JSONDecodeError:
            payload = None
        return verify_hmac_sha256(secret=secret, body=body, signature=signature, payload=payload)

    def parse_webhook(self, *, headers: dict[str, str], body: bytes) -> list[ConnectorEvent]:
        del headers
        return parse_webhook_body(body)

    def accepts(self, config: AlfredConfig, entity: ExternalEntity) -> bool:
        # Inbound ticket.created already is a Periskope ticket — do not drop it
        # because the WhatsApp group is missing from the poll allowlist.
        return _allow_entity(config, entity, enforce_chat_allowlist=False)

    def reject_reason(self, config: AlfredConfig, entity: ExternalEntity) -> str:
        if not _replication_enabled(config, entity):
            return "replicate_disabled"
        return "filtered"

    def enrich(self, config: AlfredConfig, entity: ExternalEntity) -> ExternalEntity:
        if entity.kind != "ticket":
            return entity
        enriched = entity
        try:
            client = PeriskopeApiClient.from_alfred_config(config)
            payload = client.get_ticket(entity.external_id)
            data = payload.get("ticket") if isinstance(payload.get("ticket"), dict) else payload
            if isinstance(data, dict):
                parsed = entity_from_ticket(payload if "ticket" in payload or "chat" in payload else data)
                if parsed is not None:
                    if not parsed.description and entity.description:
                        parsed.description = entity.description
                    if not parsed.chat_id:
                        parsed.chat_id = entity.chat_id
                    enriched = parsed
        except PeriskopeApiError:
            logger.debug("Periskope get_ticket failed for %s", entity.external_id, exc_info=True)
        chat_id = enriched.chat_id or entity.chat_id
        context = self._recent_chat_context(config, chat_id, limit=20)
        if context:
            existing = (enriched.description or "").strip()
            enriched.description = f"{existing}\n\n{context}".strip() if existing else context
        if chat_id:
            enriched.chat_id = chat_id
        return enriched

    def _recent_chat_context(self, config: AlfredConfig, chat_id: str, *, limit: int = 20) -> str:
        chat_id = (chat_id or "").strip()
        if not chat_id:
            return ""
        try:
            rows = self.list_messages(config, chat_id=chat_id, limit=max(1, min(limit, 20)))
        except Exception:
            logger.exception("Periskope last-messages fetch failed chat_id=%s", chat_id)
            return ""
        chronological = list(reversed(rows[:limit]))
        lines: list[str] = []
        for row in chronological:
            body = str(row.get("body") or "").strip()
            if not body:
                continue
            sender = str(row.get("sender_name") or "unknown").strip()
            stamp = str(row.get("timestamp") or "").strip()
            prefix = f"{stamp} {sender}".strip() if stamp else sender
            lines.append(f"- {prefix}: {body[:400]}")
        if not lines:
            return ""
        return "Recent WhatsApp messages:\n" + "\n".join(lines)

    def health_check(self, config: AlfredConfig) -> dict[str, Any]:
        if not self.enabled(config):
            return {"ok": False, "skipped": True, "message": "Periskope disabled"}
        settings = self.settings(config)
        token = str(getattr(settings, "api_token", "") or "").strip()
        if not token:
            return {"ok": False, "message": "Periskope API token not configured (Secrets)"}
        phone = str(getattr(settings, "org_phone", "") or "").strip()
        if not phone:
            return {"ok": False, "message": "Periskope org phone (x-phone) is required"}
        try:
            client = PeriskopeApiClient.from_alfred_config(config)
            data = client.ping()
            phones = data.get("phones") if isinstance(data, dict) else data
            count = len(phones) if isinstance(phones, list) else 1
            channel = str(
                getattr(settings, "slack_channel_id", "")
                or getattr(settings, "summary_channel_id", "")
                or ""
            ).strip()
            target = str(getattr(settings, "ticket_create_target", "slack_board") or "slack_board")
            message = f"Connected · {count} phone(s)"
            if target in {"slack_board", "both"} and not channel:
                message += " · set a Slack channel so tickets land on that channel's List"
            return {"ok": True, "message": message, "slack_channel_id": channel}
        except Exception as exc:
            return {"ok": False, "message": str(exc)}

    def list_chats(self, config: AlfredConfig) -> list[dict[str, Any]]:
        client = PeriskopeApiClient.from_alfred_config(config)
        payload = client.list_chats(limit=100)
        chats = payload.get("chats") if isinstance(payload, dict) else payload
        if not isinstance(chats, list):
            return []
        allowed = _allowed_chat_ids(config)
        out: list[dict[str, Any]] = []
        for chat in chats:
            if not isinstance(chat, dict):
                continue
            chat_id = str(chat.get("chat_id") or "").strip()
            if allowed and chat_id not in allowed:
                continue
            out.append(
                {
                    "chat_id": chat_id,
                    "chat_name": chat.get("chat_name") or "",
                    "chat_type": chat.get("chat_type") or "",
                    "labels": chat.get("chat_labels") or chat.get("labels") or "",
                }
            )
        return out

    def list_tickets(self, config: AlfredConfig, *, limit: int = 50) -> list[ExternalEntity]:
        client = PeriskopeApiClient.from_alfred_config(config)
        payload = client.list_tickets(limit=limit)
        tickets = payload.get("tickets") if isinstance(payload, dict) else payload
        if not isinstance(tickets, list):
            return []
        entities: list[ExternalEntity] = []
        for row in tickets:
            if not isinstance(row, dict):
                continue
            entity = entity_from_ticket(row)
            if entity and _allow_entity(config, entity):
                entities.append(entity)
        return entities

    def list_tasks(self, config: AlfredConfig, *, limit: int = 50) -> list[ExternalEntity]:
        client = PeriskopeApiClient.from_alfred_config(config)
        payload = client.list_tasks(limit=limit)
        tasks = payload.get("tasks") if isinstance(payload, dict) else payload
        if not isinstance(tasks, list):
            return []
        entities: list[ExternalEntity] = []
        for row in tasks:
            if not isinstance(row, dict):
                continue
            entity = entity_from_task(row)
            if entity and _allow_entity(config, entity):
                entities.append(entity)
        return entities

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
        from backend.integrations.periskope.time_range import resolve_message_window

        allowed = _allowed_chat_ids(config)
        # A specific chat_id is a targeted fetch (webhook enrich). Only apply
        # the allowlist to org-wide message pulls.
        settings = self.settings(config)
        timezone = str(getattr(settings, "summary_timezone", "") or "Asia/Kolkata")
        start, end = resolve_message_window(
            start_time,
            end_time,
            intent=intent,
            timezone=timezone,
        )
        client = PeriskopeApiClient.from_alfred_config(config)
        cap = max(1, min(int(limit or 100), 500))
        page_size = min(200, cap)
        windowed = bool(start or end)
        out: list[dict[str, Any]] = []
        offset = 0
        for _ in range(5):
            payload = client.list_messages(
                chat_id="" if windowed else chat_id,
                start_time=start,
                end_time=end,
                offset=offset,
                limit=page_size,
            )
            messages = _message_rows(payload)
            if not messages:
                break
            for message in messages:
                if not isinstance(message, dict):
                    continue
                msg_chat = str(message.get("chat_id") or message.get("to") or chat_id or "").strip()
                if chat_id and msg_chat and msg_chat != chat_id:
                    continue
                if not chat_id and allowed and msg_chat and msg_chat not in allowed:
                    continue
                out.append(_normalize_message(message, chat_id=msg_chat))
                if len(out) >= cap:
                    return out
            if len(messages) < page_size:
                break
            offset += len(messages)
        return out


def _message_rows(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in ("messages", "data", "items"):
        rows = payload.get(key)
        if isinstance(rows, list):
            return rows
    nested = payload.get("result") or payload.get("payload")
    if isinstance(nested, dict):
        rows = nested.get("messages") or nested.get("data")
        if isinstance(rows, list):
            return rows
    return []
