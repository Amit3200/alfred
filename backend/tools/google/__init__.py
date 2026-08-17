"""Google Workspace tools — Sheets and Docs."""

from __future__ import annotations

from backend.models.config import AlfredConfig
from backend.tools.google._credentials import google_credentials_ready
from backend.tools.google.docs import DOC_TOOL_NAMES, register_doc_tools
from backend.tools.google.sheets import SHEET_TOOL_NAMES, register_sheet_tools
from backend.tools.registry import ToolRegistry

GOOGLE_SHEET_TOOLS = SHEET_TOOL_NAMES
GOOGLE_DOC_TOOLS = DOC_TOOL_NAMES
GOOGLE_TOOLS = GOOGLE_SHEET_TOOLS | GOOGLE_DOC_TOOLS


def register_google_tools(registry: ToolRegistry, config: AlfredConfig) -> None:
    creds = google_credentials_ready(config)
    if creds is None:
        return
    credentials_json, refresh_token = creds
    register_sheet_tools(
        registry,
        credentials_json=credentials_json,
        refresh_token=refresh_token,
    )
    register_doc_tools(
        registry,
        credentials_json=credentials_json,
        refresh_token=refresh_token,
    )


__all__ = [
    "GOOGLE_TOOLS",
    "GOOGLE_SHEET_TOOLS",
    "GOOGLE_DOC_TOOLS",
    "register_google_tools",
]
