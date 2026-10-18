"""Summarize a WhatsApp ticket into a problem statement and action items."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from backend.integrations.periskope.copy import human_text, looks_like_wa_dump, person_label
from backend.integrations.platform.types import ExternalEntity
from backend.models.config import AlfredConfig

logger = logging.getLogger(__name__)

DEFAULT_TICKET_SUMMARY_PROMPT = """You write support tickets from WhatsApp group chats.

Return ONLY valid JSON:
{
  "title": "short action-oriented title, max 80 chars",
  "problem": "1-3 sentence problem statement in plain language",
  "action_items": ["concrete next step", "another step"]
}

Rules:
- Identify the customer's actual problem. Ignore away messages, business-hours bots, payment reminders, and WhatsApp id dumps.
- Title is what an agent should see on a board. Never paste JSON, message ids, or @g.us chat ids.
- Action items are what the team should do next (investigate, reply, fix, follow up). 1-4 bullets.
- Prefer the latest customer ask over older automated noise.
- If the chat is only a test ping, say so clearly instead of inventing a production incident.
"""

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.S | re.I)
_NOISE_RE = re.compile(
    r"business hours|thanks for reaching out|out of office|away message|"
    r"cool down period|outstanding balance|this is an automated|"
    r"your message is important|monday to saturday",
    re.I,
)
_HEX_ID_RE = re.compile(r"^[0-9A-Fa-f]{16,32}$")
_TICKET_KEY_RE = re.compile(r"^[A-Za-z]{2,12}-\d+[A-Za-z0-9-]*$")


@dataclass
class TicketIntake:
    title: str
    problem: str
    action_items: list[str] = field(default_factory=list)


def is_noise_text(text: str, *, sender: str = "") -> bool:
    body = (text or "").strip()
    if not body or looks_like_wa_dump(body):
        return True
    if _NOISE_RE.search(body):
        return True
    label = (sender or "").strip().lower()
    if label in {"api", "rules-bot", "rules-bot-no-flag"} or "rules-bot" in label:
        return True
    return False


def looks_like_ticket_id(raw: Any) -> bool:
    if isinstance(raw, dict) or raw is None:
        return False
    text = str(raw).strip()
    if not text or looks_like_wa_dump(text) or _HEX_ID_RE.fullmatch(text):
        return False
    if _TICKET_KEY_RE.fullmatch(text):
        return True
    if "-" in text and 3 <= len(text) <= 40 and " " not in text:
        return True
    return bool(re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{2,31}", text))


def clean_ticket_id(raw: Any) -> str:
    if isinstance(raw, dict) or raw is None:
        return ""
    text = str(raw).strip()
    return text if looks_like_ticket_id(text) else ""


def signal_messages(recent: list[dict[str, Any]], *, limit: int = 8) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in recent:
        body = human_text(row.get("body"))
        sender = person_label(row.get("sender_name"))
        if is_noise_text(body, sender=sender):
            continue
        out.append({**row, "body": body, "sender_name": sender or row.get("sender_name") or "Member"})
    return out[-limit:]


def heuristic_intake(
    entity: ExternalEntity,
    recent: list[dict[str, Any]] | None = None,
) -> TicketIntake:
    rows = signal_messages(list(recent or []), limit=8)
    title = human_text(entity.title)
    if looks_like_wa_dump(title):
        title = ""
    problem = ""
    for row in reversed(rows):
        if row.get("from_me"):
            continue
        body = human_text(row.get("body"))
        if body:
            problem = body
            if not title:
                title = body[:80]
            break
    if not problem:
        for row in reversed(rows):
            body = human_text(row.get("body"))
            if body:
                problem = body
                if not title:
                    title = body[:80]
                break
    if not problem:
        problem = title or "Customer raised a WhatsApp ticket; recent chat did not include a clear request."
    if not title:
        ident = entity.external_id.strip()
        title = f"WhatsApp ticket {ident}" if ident and looks_like_ticket_id(ident) else "WhatsApp ticket"
    group = human_text(entity.chat_name) or "WhatsApp group"
    return TicketIntake(
        title=title[:120],
        problem=problem[:800],
        action_items=[
            f"Investigate in {group} and reply to the customer.",
        ],
    )


def _parse_intake_json(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    match = _JSON_BLOCK_RE.search(raw)
    if match:
        raw = match.group(1)
    try:
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            return None
        parsed = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def llm_intake(
    config: AlfredConfig,
    entity: ExternalEntity,
    recent: list[dict[str, Any]],
    *,
    persona_prompt: str = "",
    extra_prompt: str = "",
    data_dir: Any = None,
) -> TicketIntake | None:
    try:
        from backend.ai.base import Message
        from backend.ai.registry import LLMRouter
        from backend.ai.routing import resolve_llm_route

        router = LLMRouter.from_config(config, data_dir=data_dir)
        _, provider, model = resolve_llm_route(config.ai, "basic_chat", router=router)
    except Exception as exc:
        logger.info("WhatsApp ticket summary: LLM unavailable: %s", exc)
        return None

    lines = []
    for row in recent[-20:]:
        sender = person_label(row.get("sender_name")) or "Member"
        body = human_text(row.get("body"))
        if not body:
            continue
        stamp = str(row.get("timestamp") or "").strip()
        prefix = f"{stamp} " if stamp else ""
        lines.append(f"{prefix}{sender}: {body}")
    if not lines:
        return None

    system = DEFAULT_TICKET_SUMMARY_PROMPT
    extra = (extra_prompt or "").strip()
    if extra:
        system = f"{system}\n\nAdditional instructions:\n{extra}"
    persona = (persona_prompt or "").strip()
    if persona:
        system = f"Channel persona (follow this first):\n{persona}\n\n{system}"

    user = "\n".join(
        [
            f"Periskope ticket: {entity.external_id}",
            f"Subject: {human_text(entity.title) or '(none)'}",
            f"WhatsApp group: {human_text(entity.chat_name) or entity.chat_id or '(unknown)'}",
            f"Raised by: {person_label((entity.extra or {}).get('raised_by')) or '(unknown)'}",
            "",
            "Recent WhatsApp messages (oldest first):",
            *lines[-20:],
        ]
    )
    try:
        response = provider.chat(
            [Message(role="system", content=system), Message(role="user", content=user[:12000])],
            model=model or None,
        )
    except Exception as exc:
        logger.warning("WhatsApp ticket summary LLM call failed: %s", exc)
        return None
    parsed = _parse_intake_json(response.content or "")
    if not parsed:
        return None
    title = human_text(parsed.get("title") or "")
    problem = human_text(parsed.get("problem") or parsed.get("summary") or "")
    raw_items = parsed.get("action_items") or parsed.get("actions") or []
    items: list[str] = []
    if isinstance(raw_items, list):
        for item in raw_items:
            text = human_text(item)
            if text:
                items.append(text[:240])
    elif isinstance(raw_items, str) and raw_items.strip():
        items.append(human_text(raw_items)[:240])
    if not title or looks_like_wa_dump(title) or not problem:
        return None
    return TicketIntake(title=title[:120], problem=problem[:1200], action_items=items[:6])


def summarize_ticket(
    config: AlfredConfig,
    entity: ExternalEntity,
    recent: list[dict[str, Any]] | None = None,
    *,
    persona_prompt: str = "",
    extra_prompt: str = "",
    data_dir: Any = None,
) -> TicketIntake:
    rows = list(recent or [])
    drafted = llm_intake(
        config,
        entity,
        rows,
        persona_prompt=persona_prompt,
        extra_prompt=extra_prompt,
        data_dir=data_dir,
    )
    if drafted is not None:
        return drafted
    return heuristic_intake(entity, rows)
