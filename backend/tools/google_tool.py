"""Google Sheets and Docs tools for the agent."""

from __future__ import annotations

import json
from typing import Any

from backend.ai.base import ToolSchema
from backend.integrations.google import docs as google_docs
from backend.integrations.google import sheets as google_sheets
from backend.integrations.google.credentials import credentials_json_type, google_libs_available
from backend.models.config import AlfredConfig
from backend.tools.registry import ToolRegistry
from backend.tools.result import ToolResult

GOOGLE_READ_SHEET = ToolSchema(
    name="google_read_sheet",
    description=(
        "Read cell values from a Google Sheet. Args: spreadsheet_id (from URL), "
        "range (A1 notation, e.g. Sheet1!A1:D10)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "spreadsheet_id": {"type": "string", "description": "Spreadsheet ID from the Google Sheets URL."},
            "range": {"type": "string", "description": "A1 range, e.g. Sheet1!A1:D10."},
        },
        "required": ["spreadsheet_id", "range"],
    },
)

GOOGLE_WRITE_SHEET = ToolSchema(
    name="google_write_sheet",
    description=(
        "Overwrite a range in a Google Sheet. Args: spreadsheet_id, range, values "
        '(JSON array of rows, e.g. [["a","b"],["c","d"]]).'
    ),
    parameters={
        "type": "object",
        "properties": {
            "spreadsheet_id": {"type": "string"},
            "range": {"type": "string"},
            "values": {
                "type": "string",
                "description": 'JSON array of rows, e.g. [["Header1","Header2"],["v1","v2"]].',
            },
        },
        "required": ["spreadsheet_id", "range", "values"],
    },
)

GOOGLE_APPEND_SHEET = ToolSchema(
    name="google_append_sheet",
    description=(
        "Append rows to a Google Sheet. Args: spreadsheet_id, range (table anchor, "
        'e.g. Sheet1!A1), values (JSON array of rows).'
    ),
    parameters={
        "type": "object",
        "properties": {
            "spreadsheet_id": {"type": "string"},
            "range": {"type": "string"},
            "values": {"type": "string", "description": "JSON array of rows."},
        },
        "required": ["spreadsheet_id", "range", "values"],
    },
)

GOOGLE_READ_DOC = ToolSchema(
    name="google_read_doc",
    description="Read plain text from a Google Doc. Args: document_id (from URL).",
    parameters={
        "type": "object",
        "properties": {
            "document_id": {"type": "string", "description": "Document ID from the Google Docs URL."},
        },
        "required": ["document_id"],
    },
)

GOOGLE_CREATE_DOC = ToolSchema(
    name="google_create_doc",
    description="Create a new Google Doc. Args: title, optional body_text (plain text).",
    parameters={
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "body_text": {"type": "string", "description": "Optional initial plain text body."},
        },
        "required": ["title"],
    },
)

GOOGLE_APPEND_DOC = ToolSchema(
    name="google_append_doc",
    description="Append plain text to an existing Google Doc. Args: document_id, text.",
    parameters={
        "type": "object",
        "properties": {
            "document_id": {"type": "string"},
            "text": {"type": "string"},
        },
        "required": ["document_id", "text"],
    },
)


def _parse_values(raw: str) -> list[list[Any]]:
    data = json.loads(raw)
    if not isinstance(data, list):
        raise ValueError("values must be a JSON array of rows")
    rows: list[list[Any]] = []
    for row in data:
        if isinstance(row, list):
            rows.append(row)
        else:
            rows.append([row])
    return rows


def _lib_error() -> ToolResult:
    return ToolResult.error(
        "Google libraries not installed. Run: pip install 'alfred-agent[google]'"
    )


def register_google_tools(registry: ToolRegistry, config: AlfredConfig) -> None:
    if not config.google.enabled:
        return

    credentials_json = (config.google.credentials_json or "").strip()
    if not credentials_json:
        return

    try:
        cred_type = credentials_json_type(credentials_json)
    except ValueError:
        return

    refresh_token = (config.google.oauth_refresh_token or "").strip()
    if cred_type == "oauth_client" and not refresh_token:
        return

    def read_sheet_handler(args: dict[str, Any]) -> ToolResult:
        if not google_libs_available():
            return _lib_error()
        spreadsheet_id = str(args.get("spreadsheet_id") or "").strip()
        range_a1 = str(args.get("range") or "").strip()
        if not spreadsheet_id or not range_a1:
            return ToolResult.error("spreadsheet_id and range are required.")
        try:
            data = google_sheets.read_sheet(
                spreadsheet_id=spreadsheet_id,
                range_a1=range_a1,
                credentials_json=credentials_json,
                refresh_token=refresh_token,
            )
            return ToolResult(kind="google_sheet", data={"action": "read", **data})
        except Exception as exc:
            return ToolResult.error(str(exc))

    def write_sheet_handler(args: dict[str, Any]) -> ToolResult:
        if not google_libs_available():
            return _lib_error()
        spreadsheet_id = str(args.get("spreadsheet_id") or "").strip()
        range_a1 = str(args.get("range") or "").strip()
        values_raw = str(args.get("values") or "")
        if not spreadsheet_id or not range_a1 or not values_raw:
            return ToolResult.error("spreadsheet_id, range, and values are required.")
        try:
            rows = _parse_values(values_raw)
            data = google_sheets.write_sheet(
                spreadsheet_id=spreadsheet_id,
                range_a1=range_a1,
                values=rows,
                credentials_json=credentials_json,
                refresh_token=refresh_token,
            )
            return ToolResult(kind="google_sheet", data={"action": "write", **data})
        except Exception as exc:
            return ToolResult.error(str(exc))

    def append_sheet_handler(args: dict[str, Any]) -> ToolResult:
        if not google_libs_available():
            return _lib_error()
        spreadsheet_id = str(args.get("spreadsheet_id") or "").strip()
        range_a1 = str(args.get("range") or "").strip()
        values_raw = str(args.get("values") or "")
        if not spreadsheet_id or not range_a1 or not values_raw:
            return ToolResult.error("spreadsheet_id, range, and values are required.")
        try:
            rows = _parse_values(values_raw)
            data = google_sheets.append_sheet(
                spreadsheet_id=spreadsheet_id,
                range_a1=range_a1,
                values=rows,
                credentials_json=credentials_json,
                refresh_token=refresh_token,
            )
            return ToolResult(kind="google_sheet", data={"action": "append", **data})
        except Exception as exc:
            return ToolResult.error(str(exc))

    def read_doc_handler(args: dict[str, Any]) -> ToolResult:
        if not google_libs_available():
            return _lib_error()
        document_id = str(args.get("document_id") or "").strip()
        if not document_id:
            return ToolResult.error("document_id is required.")
        try:
            data = google_docs.read_doc(
                document_id=document_id,
                credentials_json=credentials_json,
                refresh_token=refresh_token,
            )
            return ToolResult(kind="google_doc", data={"action": "read", **data})
        except Exception as exc:
            return ToolResult.error(str(exc))

    def create_doc_handler(args: dict[str, Any]) -> ToolResult:
        if not google_libs_available():
            return _lib_error()
        title = str(args.get("title") or "").strip()
        if not title:
            return ToolResult.error("title is required.")
        try:
            data = google_docs.create_doc(
                title=title,
                body_text=str(args.get("body_text") or ""),
                credentials_json=credentials_json,
                refresh_token=refresh_token,
            )
            return ToolResult(kind="google_doc", data={"action": "create", **data})
        except Exception as exc:
            return ToolResult.error(str(exc))

    def append_doc_handler(args: dict[str, Any]) -> ToolResult:
        if not google_libs_available():
            return _lib_error()
        document_id = str(args.get("document_id") or "").strip()
        text = str(args.get("text") or "")
        if not document_id or not text:
            return ToolResult.error("document_id and text are required.")
        try:
            data = google_docs.append_doc(
                document_id=document_id,
                text=text,
                credentials_json=credentials_json,
                refresh_token=refresh_token,
            )
            return ToolResult(kind="google_doc", data={"action": "append", **data})
        except Exception as exc:
            return ToolResult.error(str(exc))

    registry.register(GOOGLE_READ_SHEET, read_sheet_handler)
    registry.register(GOOGLE_WRITE_SHEET, write_sheet_handler)
    registry.register(GOOGLE_APPEND_SHEET, append_sheet_handler)
    registry.register(GOOGLE_READ_DOC, read_doc_handler)
    registry.register(GOOGLE_CREATE_DOC, create_doc_handler)
    registry.register(GOOGLE_APPEND_DOC, append_doc_handler)
