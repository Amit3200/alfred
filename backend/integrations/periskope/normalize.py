"""Normalize Periskope tickets/tasks/webhooks into ExternalEntity."""

from __future__ import annotations

import json
from typing import Any

from backend.integrations.periskope.copy import human_text, person_label
from backend.integrations.periskope.summarize import clean_ticket_id
from backend.integrations.platform.types import ConnectorEvent, ExternalEntity

CONNECTOR_ID = "periskope"

_TICKET_EVENTS = frozenset({"ticket.created", "ticket.updated", "ticket.deleted"})
_TASK_EVENTS = frozenset({"task.created", "task.updated", "task.deleted"})
IGNORED_EVENTS = frozenset(
    {
        "message.created",
        "message.updated",
        "message.deleted",
        "message.ack.updated",
        "chat.created",
        "chat.notification.created",
    }
)
_IGNORED_EVENTS = IGNORED_EVENTS


def _priority_label(raw: Any) -> str:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        text = str(raw or "").strip().lower()
        if text in {"high", "p0", "p1", "urgent", "critical"}:
            return "High"
        if text in {"low", "p3"}:
            return "Low"
        return "Medium"
    if value >= 3:
        return "High"
    if value <= 0:
        return "Low"
    return "Medium"


def _labels(raw: Any) -> list[str]:
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    text = str(raw or "").strip()
    if not text:
        return []
    return [part.strip() for part in text.split(",") if part.strip()]


def _ticket_payload(data: dict[str, Any]) -> dict[str, Any]:
    ticket = data.get("ticket")
    if isinstance(ticket, dict):
        return ticket
    return data


def _chat_payload(data: dict[str, Any]) -> dict[str, Any]:
    chat = data.get("chat")
    return chat if isinstance(chat, dict) else {}


def _message_bodies(data: dict[str, Any]) -> str:
    chunks: list[str] = []
    message = data.get("message")
    if isinstance(message, dict):
        body = human_text(message.get("body") or message)
        if body:
            chunks.append(body)
    attached = data.get("attached_messages")
    if isinstance(attached, list):
        for item in attached:
            if isinstance(item, dict):
                body = human_text(item.get("body") or item)
                if body:
                    chunks.append(body)
    return "\n".join(part for part in chunks if part)[:4000]


def entity_from_ticket(data: dict[str, Any], *, action: str = "upsert") -> ExternalEntity | None:
    ticket = _ticket_payload(data)
    chat = _chat_payload(data)
    message = data.get("message") if isinstance(data.get("message"), dict) else {}
    ticket_id = (
        clean_ticket_id(ticket.get("ticket_id"))
        or clean_ticket_id(data.get("ticket_id"))
        or clean_ticket_id(message.get("ticket_id"))
        or clean_ticket_id(ticket.get("id"))
    )
    title = human_text(ticket.get("subject") or data.get("subject") or "")
    if not title:
        title = human_text(message.get("body") or message)
    if not ticket_id:
        return None
    if not title:
        title = f"WhatsApp ticket {ticket_id}"
    status = str(ticket.get("status") or "").strip()
    entity_action = "close" if action == "close" or status.lower() in {"closed", "deleted"} else "upsert"
    if ticket.get("is_deleted"):
        entity_action = "close"
    raised = person_label(
        ticket.get("raised_by")
        or ticket.get("created_by")
        or ticket.get("customer_name")
        or message.get("sender_name")
        or message.get("performed_by")
        or message.get("author")
    )
    chat_id = str(
        chat.get("chat_id")
        or ticket.get("chat_id")
        or message.get("chat_id")
        or (message.get("id") or {}).get("remote")
        or ""
    ).strip()
    if isinstance(message.get("id"), dict) and not chat_id:
        chat_id = str(message["id"].get("remote") or "").strip()
    return ExternalEntity(
        connector_id=CONNECTOR_ID,
        kind="ticket",
        external_id=ticket_id,
        title=title,
        description=_message_bodies(data),
        status=status,
        priority=_priority_label(ticket.get("priority")),
        assignee_hint=str(ticket.get("assignee") or "").strip(),
        labels=_labels(ticket.get("ticket_labels") or ticket.get("labels")),
        chat_id=chat_id,
        chat_name=str(chat.get("chat_name") or chat.get("name") or "").strip(),
        action=entity_action,  # type: ignore[arg-type]
        extra={"raw_status": status, "raised_by": raised},
    )


def entity_from_task(data: dict[str, Any], *, action: str = "upsert") -> ExternalEntity | None:
    task = data.get("task") if isinstance(data.get("task"), dict) else data
    task_id = str(task.get("task_id") or "").strip()
    title = str(task.get("title") or "").strip()
    if not task_id or not title:
        return None
    status = str(task.get("status") or "").strip()
    entity_action = "close" if action == "close" or status.lower() in {"closed", "completed"} else "upsert"
    notes = str(task.get("notes") or "").strip()
    return ExternalEntity(
        connector_id=CONNECTOR_ID,
        kind="task",
        external_id=task_id,
        title=title,
        description=notes,
        status=status,
        priority=_priority_label(task.get("priority")),
        assignee_hint=str(task.get("assignee") or "").strip(),
        chat_id=str(task.get("chat_id") or "").strip(),
        action=entity_action,  # type: ignore[arg-type]
    )


def parse_webhook_body(body: bytes) -> list[ConnectorEvent]:
    payload = json.loads(body or b"{}")
    if not isinstance(payload, dict):
        return []
    event_type = str(
        payload.get("event_type") or payload.get("event") or payload.get("type") or ""
    ).strip()
    data = payload.get("data")
    if not isinstance(data, dict):
        data = payload
    if event_type in _IGNORED_EVENTS or not event_type:
        if event_type in _IGNORED_EVENTS:
            return [
                ConnectorEvent(
                    connector_id=CONNECTOR_ID,
                    event_type=event_type,
                    entity=None,
                    raw=payload,
                )
            ]
        return []

    action = "close" if event_type.endswith(".deleted") else "upsert"
    entity: ExternalEntity | None = None
    needs_enrich = False
    if event_type in _TICKET_EVENTS:
        entity = entity_from_ticket(data, action=action)
        needs_enrich = True
    elif event_type in _TASK_EVENTS:
        entity = entity_from_task(data, action=action)
    elif event_type in {"message.ticket.attached", "message.flagged"}:
        entity = entity_from_ticket(data, action="upsert")
        needs_enrich = True
    return [
        ConnectorEvent(
            connector_id=CONNECTOR_ID,
            event_type=event_type,
            entity=entity,
            needs_enrich=needs_enrich,
            raw=payload,
        )
    ]
