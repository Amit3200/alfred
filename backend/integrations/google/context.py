"""Google Workspace context — connection status and prompt blocks."""

from __future__ import annotations

import re
from typing import Any

from backend.health import check_google
from backend.models.config import AlfredConfig
from backend.models.task import Task

_SHEET_URL_RE = re.compile(
    r"https?://docs\.google\.com/spreadsheets/d/([a-zA-Z0-9-_]+)",
    re.I,
)
_DOC_URL_RE = re.compile(
    r"https?://docs\.google\.com/document/d/([a-zA-Z0-9-_]+)",
    re.I,
)
_ACCESS_HINTS = (
    "google access",
    "workspace access",
    "connected to google",
    "google connected",
    "have access",
    "is it working",
    "does it work",
    "can you access",
)


def format_google_context_for_prompt(
    config: AlfredConfig,
    task: Task,
    session: Any | None = None,
) -> str:
    """Inject Google Workspace connection status into the system prompt."""
    google = config.google
    if not google.enabled:
        return ""

    status = check_google(config)
    parts: list[str] = ["## Google Workspace context"]

    if status.get("skipped"):
        parts.append("- Integration is **disabled** in config.")
        return "\n".join(parts)

    if status.get("ok"):
        parts.append(f"- Connection: **connected** — {status.get('message', 'OK')}.")
        parts.append(
            "- You **have** Google Sheets and Docs access via `google_read_sheet`, "
            "`google_write_sheet`, `google_append_sheet`, `google_read_doc`, "
            "`google_create_doc`, and `google_append_doc`."
        )
        parts.append(
            "- **Never** claim you lack Google access or invent spreadsheet/doc content. "
            "Use the Google tools to read or write real data."
        )
    else:
        parts.append(f"- Connection: **not ready** — {status.get('message', 'Unknown error')}.")
        parts.append(
            "- Tell the user to finish setup in Admin → Secrets / Integrations → Connect Google."
        )
        parts.append("- Do not claim you successfully read or wrote Google files until connected.")

    history = [task.cleaned_intent, task.raw_text]
    if session:
        history.extend(turn.content for turn in session.turns[-6:])

    sheet_ids: list[str] = []
    doc_ids: list[str] = []
    for text in history:
        for match in _SHEET_URL_RE.finditer(text or ""):
            sheet_id = match.group(1)
            if sheet_id not in sheet_ids:
                sheet_ids.append(sheet_id)
        for match in _DOC_URL_RE.finditer(text or ""):
            doc_id = match.group(1)
            if doc_id not in doc_ids:
                doc_ids.append(doc_id)

    if sheet_ids:
        parts.append(
            "- Spreadsheet ID(s) in this thread: "
            + ", ".join(f"`{sid}`" for sid in sheet_ids[:3])
        )
    if doc_ids:
        parts.append(
            "- Document ID(s) in this thread: "
            + ", ".join(f"`{did}`" for did in doc_ids[:3])
        )

    if looks_like_google_access_question(task.cleaned_intent):
        if status.get("ok"):
            parts.append(
                "- User is asking whether Google access works — confirm it is connected "
                "and offer to read/write a sheet or doc with the tools."
            )
        else:
            parts.append(
                "- User is asking whether Google access works — explain the connection "
                "issue above and how to fix it."
            )

    return "\n".join(parts)


def looks_like_google_access_question(intent: str) -> bool:
    lower = (intent or "").lower()
    if "google" not in lower and "workspace" not in lower and "sheet" not in lower:
        if not any(h in lower for h in _ACCESS_HINTS):
            return False
    return any(h in lower for h in _ACCESS_HINTS)
