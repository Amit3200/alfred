"""Human-readable WhatsApp ticket copy for Slack Lists and channel cards."""

from __future__ import annotations

from typing import Any

from backend.integrations.platform.types import ExternalEntity

_JUNK_MARKERS = ("from_me", "serialized", "'remote'", '"remote"', "'id':", '"id":')
_TEXT_KEYS = ("body", "text", "caption", "message", "content", "msg")


def looks_like_wa_dump(text: str) -> bool:
    value = (text or "").strip()
    if not value:
        return True
    lowered = value.lower()
    if value.startswith("{") and any(marker in lowered for marker in _JUNK_MARKERS):
        return True
    if "serialized" in lowered and "@g.us" in lowered:
        return True
    if value.endswith("@g.us"):
        return True
    return False


def human_text(raw: Any) -> str:
    if raw is None:
        return ""
    if isinstance(raw, dict):
        for key in _TEXT_KEYS:
            nested = raw.get(key)
            if isinstance(nested, str) and nested.strip() and not looks_like_wa_dump(nested):
                return nested.strip()
        return ""
    text = str(raw).strip()
    if looks_like_wa_dump(text):
        return ""
    return " ".join(text.split())


def person_label(raw: Any) -> str:
    if raw is None:
        return ""
    if isinstance(raw, dict):
        for key in ("name", "sender_name", "pushname", "notify", "email"):
            label = person_label(raw.get(key))
            if label:
                return label
        return ""
    text = str(raw).strip()
    if not text or looks_like_wa_dump(text) or text.lower() in {"unknown", "none", "null"}:
        return ""
    if "@" in text and not text.endswith(("@g.us", "@c.us")):
        return text
    if text.endswith(("@g.us", "@c.us")):
        return text.split("@", 1)[0]
    return text


def ticket_title(*, subject: str = "", message_body: str = "", recent: list[dict[str, Any]] | None = None, ticket_id: str = "") -> str:
    for candidate in (human_text(subject), human_text(message_body)):
        if candidate:
            return candidate[:120]
    for row in reversed(list(recent or [])):
        if row.get("from_me"):
            continue
        body = human_text(row.get("body"))
        if body:
            return body[:120]
    for row in reversed(list(recent or [])):
        body = human_text(row.get("body"))
        if body:
            return body[:120]
    ident = (ticket_id or "").strip()
    return f"WhatsApp ticket {ident}" if ident else "WhatsApp ticket"


def group_label(entity: ExternalEntity) -> str:
    name = human_text(entity.chat_name)
    if name:
        return name
    extra = entity.extra or {}
    name = human_text(extra.get("group_name") or extra.get("chat_name"))
    return name or "WhatsApp group"


def raised_by(entity: ExternalEntity, recent: list[dict[str, Any]] | None = None) -> str:
    extra = entity.extra or {}
    for candidate in (
        extra.get("raised_by"),
        entity.assignee_hint,
    ):
        label = person_label(candidate)
        if label:
            return label
    for row in reversed(list(recent or [])):
        if row.get("from_me"):
            continue
        label = person_label(row.get("sender_name"))
        if label:
            return label
    for row in reversed(list(recent or [])):
        label = person_label(row.get("sender_name"))
        if label:
            return label
    return "Unknown"


def recent_quotes(recent: list[dict[str, Any]], *, limit: int = 5) -> list[str]:
    quotes: list[str] = []
    for row in recent[-limit:]:
        body = human_text(row.get("body"))
        if not body:
            continue
        sender = person_label(row.get("sender_name")) or "Member"
        quotes.append(f"{sender}: {body[:280]}")
    return quotes


def _mrkdwn_escape(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def issue_summary(entity: ExternalEntity, recent: list[dict[str, Any]] | None = None) -> str:
    intake = (entity.extra or {}).get("intake") or {}
    problem = human_text(intake.get("problem") if isinstance(intake, dict) else "")
    if problem:
        return problem
    quotes = recent_quotes(recent or [], limit=5)
    title = human_text(entity.title)
    if title and not looks_like_wa_dump(title):
        return title
    if quotes:
        return quotes[-1].split(": ", 1)[-1]
    return "New WhatsApp ticket."


def _intake_action_items(entity: ExternalEntity) -> list[str]:
    intake = (entity.extra or {}).get("intake") or {}
    if not isinstance(intake, dict):
        return []
    raw = intake.get("action_items") or []
    if not isinstance(raw, list):
        return []
    return [human_text(item) for item in raw if human_text(item)]


def list_item_details(entity: ExternalEntity, recent: list[dict[str, Any]] | None = None) -> str:
    """Compact Details column for the Slack List card (Merchant / Issue / actions)."""
    rows = list(recent or entity.extra.get("recent_messages") or [])
    group = group_label(entity)
    lines = [
        f"Merchant: {group}",
        f"Issue: {issue_summary(entity, rows)}",
    ]
    items = _intake_action_items(entity)
    if items:
        lines.append("Action items: " + "; ".join(items))
    lines.append(f"Raised by: {raised_by(entity, rows)}")
    lines.append(f"Periskope: {entity.external_id}")
    return "\n".join(lines)[:8000]


def announce_fallback(entity: ExternalEntity, *, display_id: str = "") -> str:
    title = human_text(entity.title) or issue_summary(entity, entity.extra.get("recent_messages") or [])
    prefix = display_id or entity.external_id or "ticket"
    return f"{prefix} · {title}"


def announce_color(priority: str) -> str:
    return {
        "High": "#E01E5A",
        "Medium": "#ECB22E",
        "Low": "#2EB67D",
    }.get((priority or "Medium").strip(), "#ECB22E")


def _severity_label(priority: str) -> str:
    value = (priority or "Medium").strip() or "Medium"
    mark = {"High": "🔴", "Medium": "🟡", "Low": "🟢"}.get(value, "🟡")
    return f"{mark} {value}"


def announce_blocks(
    entity: ExternalEntity,
    *,
    display_id: str = "",
    list_url: str = "",
    jira_key: str = "",
    board_name: str = "",
    status: str = "Not picked",
) -> list[dict[str, Any]]:
    """Channel card: title, metadata fields, details, open-list button."""
    recent = list(entity.extra.get("recent_messages") or [])
    title = human_text(entity.title) or issue_summary(entity, recent)
    group = group_label(entity)
    ticket_ref = display_id or entity.external_id or "ticket"
    subtitle_parts = [ticket_ref]
    if board_name:
        subtitle_parts.append(f"Item in {board_name}")
    else:
        subtitle_parts.append("WhatsApp ticket")
    heading = f"*{_mrkdwn_escape(title[:120])}*\n{_mrkdwn_escape(' · '.join(subtitle_parts))}"
    fields = [
        {"type": "mrkdwn", "text": f"*Severity*\n{_severity_label(entity.priority)}"},
        {"type": "mrkdwn", "text": f"*Status*\n{_mrkdwn_escape(status or 'Not picked')}"},
        {"type": "mrkdwn", "text": f"*Submitted by*\n{_mrkdwn_escape(raised_by(entity, recent))}"},
        {"type": "mrkdwn", "text": f"*WhatsApp group*\n{_mrkdwn_escape(group)}"},
        {"type": "mrkdwn", "text": f"*Periskope*\n`{_mrkdwn_escape(entity.external_id)}`"},
        {"type": "mrkdwn", "text": f"*Ticket*\n`{_mrkdwn_escape(ticket_ref)}`"},
    ]
    if jira_key:
        fields.append({"type": "mrkdwn", "text": f"*JIRA*\n`{_mrkdwn_escape(jira_key)}`"})
    problem = _mrkdwn_escape(issue_summary(entity, recent))
    details = [
        "*Details*",
        f"Merchant: {_mrkdwn_escape(group)}",
        f"Issue: {problem}",
    ]
    items = _intake_action_items(entity)
    if items:
        details.extend(["", "*Action items*"])
        details.extend(f"• {_mrkdwn_escape(item)}" for item in items)
    blocks: list[dict[str, Any]] = [
        {"type": "section", "text": {"type": "mrkdwn", "text": heading[:2900]}},
        {"type": "section", "fields": fields[:10]},
        {"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(details)[:2900]}},
    ]
    if list_url.startswith(("http://", "https://")):
        blocks.append(
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Open in Slack List"},
                        "url": list_url,
                        "action_id": "open_periskope_list_item",
                    }
                ],
            }
        )
    elif list_url:
        blocks.append(
            {
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": f"<{list_url}|Open Slack List item>"}],
            }
        )
    return blocks
