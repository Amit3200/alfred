"""Confirmation phrase detection and session-scoped write approval."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.models.config import GovernanceConfig
from backend.models.session import ConversationSession

_DEFAULT_PHRASES = (
    "yes, proceed",
    "yes proceed",
    "proceed",
    "confirm",
    "confirmed",
    "approved",
    "approve",
    "go ahead",
    "lgtm",
    "yes do it",
    "yes, do it",
)

_APPROVAL_KEY = "governance_write_approval"


def _phrases(config: GovernanceConfig) -> tuple[str, ...]:
    custom = tuple(p.strip().lower() for p in config.confirmation_phrases if p.strip())
    return custom or _DEFAULT_PHRASES


def is_confirmation_phrase(text: str, config: GovernanceConfig) -> bool:
    lower = (text or "").strip().lower()
    if not lower:
        return False
    for phrase in _phrases(config):
        if lower == phrase or lower.startswith(phrase + " ") or lower.endswith(" " + phrase):
            return True
        if phrase in lower and len(lower) <= len(phrase) + 20:
            return True
    return bool(re.match(r"^yes\s*,?\s*proceed\.?$", lower))


def is_confirmation_only(text: str, config: GovernanceConfig) -> bool:
    """True when the message is only a confirmation (no new task)."""
    lower = (text or "").strip().lower()
    if not is_confirmation_phrase(lower, config):
        return False
    stripped = re.sub(r"^(?:@alfred\s+)?", "", lower).strip()
    return len(stripped) <= 40


def approval_metadata_patch(
    *,
    user_id: str,
    ttl_minutes: int,
) -> dict[str, Any]:
    expires = datetime.now(timezone.utc) + timedelta(minutes=max(1, ttl_minutes))
    return {
        _APPROVAL_KEY: {
            "approved": True,
            "approved_at": datetime.now(timezone.utc).isoformat(),
            "approved_by": user_id,
            "expires_at": expires.isoformat(),
        }
    }


def session_has_write_approval(
    session: ConversationSession | None,
    config: GovernanceConfig,
) -> bool:
    if not config.enabled or not config.require_confirmation:
        return True
    if session is None:
        return False
    bucket = session.metadata.get(_APPROVAL_KEY)
    if not isinstance(bucket, dict) or not bucket.get("approved"):
        return False
    expires_raw = bucket.get("expires_at")
    if expires_raw:
        try:
            expires = datetime.fromisoformat(str(expires_raw))
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) > expires:
                return False
        except ValueError:
            pass
    return True


def confirmation_required_message(tool_name: str, summary: str) -> str:
    return (
        f"Governance: `{tool_name}` requires explicit approval before I can run it.\n"
        f"Planned action: {summary}\n"
        "Reply *yes, proceed* in this thread to approve write actions for the next 30 minutes, "
        "then ask me to continue (or repeat your request)."
    )


def confirmation_required_board_batch_message(titles: list[str]) -> str:
    cleaned = [t.strip() for t in titles if (t or "").strip()]
    if not cleaned:
        return confirmation_required_message("slack_board_create_task", "create Slack List tasks")
    listed = "\n".join(f"- {title}" for title in cleaned)
    return (
        "Governance: `slack_board_create_task` requires explicit approval before I can run it.\n"
        f"I'll create **{len(cleaned)}** Slack List tasks:\n{listed}\n"
        "Reply *yes, proceed* in this thread and I'll create them."
    )


def confirmation_granted_message(ttl_minutes: int) -> str:
    return (
        f"*Write actions approved* for this thread for the next {ttl_minutes} minutes.\n"
        "You can repeat your `@alfred pr` request or tell me to continue where we left off."
    )
