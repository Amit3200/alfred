"""Google Sheets tool schemas."""

from __future__ import annotations

from backend.ai.base import ToolSchema

GOOGLE_CREATE_SHEET = ToolSchema(
    name="google_create_sheet",
    description=(
        "Create a NEW Google Spreadsheet. Returns spreadsheet_id and URL. "
        "Use google_write_sheet or google_append_sheet to update an existing sheet."
    ),
    parameters={
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Spreadsheet title."},
            "sheet_name": {
                "type": "string",
                "description": "First tab name (default Sheet1).",
            },
            "headers": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional header row.",
            },
            "rows": {
                "type": "array",
                "items": {"type": "array", "items": {}},
                "description": "Optional initial data rows (array of arrays).",
            },
        },
        "required": ["title"],
    },
)

GOOGLE_READ_SHEET = ToolSchema(
    name="google_read_sheet",
    description=(
        "Read cell values from an EXISTING Google Sheet. "
        "Args: spreadsheet_id (from URL), range (A1 notation, e.g. Sheet1!A1:D10)."
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
        "Overwrite a range in an EXISTING Google Sheet. "
        "Args: spreadsheet_id, range, rows (array of row arrays)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "spreadsheet_id": {"type": "string"},
            "range": {"type": "string"},
            "rows": {
                "type": "array",
                "items": {"type": "array", "items": {}},
                "description": "Rows to write, e.g. [[\"A\",\"B\"],[\"1\",\"2\"]].",
            },
            "values": {
                "type": "string",
                "description": "Deprecated: JSON string of rows. Prefer `rows` array.",
            },
        },
        "required": ["spreadsheet_id", "range"],
    },
)

GOOGLE_APPEND_SHEET = ToolSchema(
    name="google_append_sheet",
    description=(
        "Append rows to an EXISTING Google Sheet. "
        "Args: spreadsheet_id, range (table anchor, e.g. Sheet1!A1), rows."
    ),
    parameters={
        "type": "object",
        "properties": {
            "spreadsheet_id": {"type": "string"},
            "range": {"type": "string"},
            "rows": {
                "type": "array",
                "items": {"type": "array", "items": {}},
                "description": "Rows to append.",
            },
            "values": {
                "type": "string",
                "description": "Deprecated: JSON string of rows. Prefer `rows` array.",
            },
        },
        "required": ["spreadsheet_id", "range"],
    },
)

SHEET_TOOL_NAMES = frozenset(
    {
        "google_create_sheet",
        "google_read_sheet",
        "google_write_sheet",
        "google_append_sheet",
    }
)
