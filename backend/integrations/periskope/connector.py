"""Periskope connector — WhatsApp tickets/tasks/messages into Alfred."""

from __future__ import annotations

import json
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


def _allowed_chat_ids(config: AlfredConfig) -> set[str]:
    settings = getattr(getattr(config, "connectors", None), "periskope", None)
    raw = list(getattr(settings, "allowed_chat_ids", None) or [])
    return {str(item).strip() for item in raw if str(item).strip()}


def _allow_entity(config: AlfredConfig, entity: ExternalEntity) -> bool:
    settings = getattr(getattr(config, "connectors", None), "periskope", None)
    if entity.kind == "ticket" and not bool(getattr(settings, "replicate_tickets", True)):
        return False
    if entity.kind == "task" and not bool(getattr(settings, "replicate_tasks", True)):
        return False
    allowed = _allowed_chat_ids(config)
    if allowed and entity.chat_id and entity.chat_id not in allowed:
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
        return _allow_entity(config, entity)

    def enrich(self, config: AlfredConfig, entity: ExternalEntity) -> ExternalEntity:
        if entity.kind != "ticket":
            return entity
        try:
            client = PeriskopeApiClient.from_alfred_config(config)
            payload = client.get_ticket(entity.external_id)
            data = payload.get("ticket") if isinstance(payload.get("ticket"), dict) else payload
            if not isinstance(data, dict):
                return entity
            enriched = entity_from_ticket(payload if "ticket" in payload or "chat" in payload else data)
            return enriched or entity
        except PeriskopeApiError:
            return entity

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
            return {"ok": True, "message": f"Connected · {count} phone(s)"}
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
        if allowed and chat_id and chat_id not in allowed:
            return []
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
                if allowed and msg_chat and msg_chat not in allowed:
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
