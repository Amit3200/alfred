"""Session-scoped pending Slack List creates (governance resume)."""

from __future__ import annotations

from typing import Any

PENDING_BOARD_CREATES_KEY = "pending_board_creates"


def remember_pending_board_create(
    session: Any | None,
    *,
    title: str,
    severity: str = "",
    assignee_user_id: str = "",
) -> None:
    """Append a planned board create so *yes, proceed* can finish it."""
    cleaned = (title or "").strip()
    if session is None or not cleaned:
        return
    meta = dict(getattr(session, "metadata", None) or {})
    pending = list(meta.get(PENDING_BOARD_CREATES_KEY) or [])
    if any(str(item.get("title") or "").strip().lower() == cleaned.lower() for item in pending):
        session.metadata = meta
        return
    pending.append(
        {
            "title": cleaned[:200],
            "severity": (severity or "").strip(),
            "assignee_user_id": (assignee_user_id or "").strip(),
        }
    )
    meta[PENDING_BOARD_CREATES_KEY] = pending
    session.metadata = meta


def get_pending_board_creates(session: Any | None) -> list[dict[str, str]]:
    if session is None:
        return []
    raw = list((getattr(session, "metadata", None) or {}).get(PENDING_BOARD_CREATES_KEY) or [])
    titles: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        titles.append(
            {
                "title": title[:200],
                "severity": str(item.get("severity") or "").strip(),
                "assignee_user_id": str(item.get("assignee_user_id") or "").strip(),
            }
        )
    return titles


def pending_board_creates_patch(session: Any | None) -> dict[str, Any]:
    pending = get_pending_board_creates(session)
    if not pending:
        return {}
    return {PENDING_BOARD_CREATES_KEY: pending}


def clear_pending_board_creates_patch() -> dict[str, Any]:
    return {PENDING_BOARD_CREATES_KEY: []}
