"""Parse Slack message payloads into plain text."""

from __future__ import annotations

from datetime import datetime, timezone


def extract_message_text(message: dict) -> str:
    from backend.ingress.sanitize import clean_slack_text

    parts: list[str] = []

    main = clean_slack_text(message.get("text") or "")
    if main:
        parts.append(main)

    for attachment in message.get("attachments") or []:
        for key in ("pretext", "title", "text", "fallback"):
            value = attachment.get(key)
            if value:
                parts.append(clean_slack_text(str(value)))
        for field in attachment.get("fields") or []:
            title = field.get("title") or ""
            value = field.get("value") or ""
            if title or value:
                parts.append(clean_slack_text(f"{title}: {value}".strip(": ")))

    for block in message.get("blocks") or []:
        block_type = block.get("type")
        if block_type in ("section", "header"):
            text_obj = block.get("text") or {}
            if text_obj.get("text"):
                parts.append(clean_slack_text(text_obj["text"]))
        elif block_type == "context":
            for element in block.get("elements") or []:
                if element.get("text"):
                    parts.append(clean_slack_text(element["text"]))

    seen: set[str] = set()
    unique: list[str] = []
    for part in parts:
        part = part.strip()
        if part and part not in seen:
            seen.add(part)
            unique.append(part)
    return "\n".join(unique)


def format_slack_message(
    message: dict,
    *,
    user_names: dict[str, str] | None = None,
) -> str | None:
    text = extract_message_text(message)
    if not text:
        return None

    author = _message_author(message)
    when = format_slack_ts(message.get("ts") or "")
    line = f"{when} | {author}: {text}"
    reactions = _format_reactions(message, user_names=user_names)
    if reactions:
        line = f"{line} | {reactions}"
    return line


def _format_reactions(message: dict, *, user_names: dict[str, str] | None = None) -> str:
    from backend.ingress.slack_users import format_user_list

    reactions = message.get("reactions") or []
    if not reactions:
        return ""
    parts: list[str] = []
    for reaction in reactions:
        name = reaction.get("name", "?")
        users = reaction.get("users") or []
        if users:
            parts.append(f":{name}: by {format_user_list(users, user_names)}")
        else:
            parts.append(f":{name}: x{reaction.get('count', 1)}")
    return "reactions: " + "; ".join(parts)


def _message_author(message: dict) -> str:
    if message.get("username"):
        return f"{message['username']} (app)"
    if message.get("bot_id"):
        return "bot (app)"
    return message.get("user") or "user"


def format_slack_ts(ts: str) -> str:
    try:
        seconds = float(str(ts).split(".")[0])
        return datetime.fromtimestamp(seconds, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except (ValueError, OSError, TypeError):
        return str(ts)
