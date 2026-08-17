"""Google Sheets tool handlers."""

from __future__ import annotations

import json
from typing import Any

from backend.integrations.google import sheets as google_sheets
from backend.integrations.google.credentials import google_libs_available
from backend.tools.google.sheets.schemas import (
    GOOGLE_APPEND_SHEET,
    GOOGLE_CREATE_SHEET,
    GOOGLE_READ_SHEET,
    GOOGLE_WRITE_SHEET,
)
from backend.tools.registry import ToolRegistry
from backend.tools.result import ToolResult


def _lib_error() -> ToolResult:
    return ToolResult.error(
        "Google libraries not installed. Run: pip install 'alfred-agent[google]'"
    )


def _parse_rows(args: dict[str, Any]) -> list[list[Any]]:
    if rows := args.get("rows"):
        if not isinstance(rows, list):
            raise ValueError("rows must be an array of row arrays.")
        return [list(row) if isinstance(row, list) else [row] for row in rows]
    values_raw = str(args.get("values") or "").strip()
    if not values_raw:
        raise ValueError("rows or values is required.")
    data = json.loads(values_raw)
    if not isinstance(data, list):
        raise ValueError("values must be a JSON array of rows")
    parsed: list[list[Any]] = []
    for row in data:
        parsed.append(list(row) if isinstance(row, list) else [row])
    return parsed


def _parse_headers(args: dict[str, Any]) -> list[Any] | None:
    headers = args.get("headers")
    if headers is None:
        return None
    if not isinstance(headers, list):
        raise ValueError("headers must be an array of strings.")
    return list(headers)


def register_sheet_tools(
    registry: ToolRegistry,
    *,
    credentials_json: str,
    refresh_token: str,
) -> None:
    def create_handler(args: dict[str, Any]) -> ToolResult:
        if not google_libs_available():
            return _lib_error()
        title = str(args.get("title") or "").strip()
        if not title:
            return ToolResult.error("title is required.")
        try:
            headers = _parse_headers(args)
            rows = _parse_rows(args) if args.get("rows") or args.get("values") else None
            data = google_sheets.create_spreadsheet(
                title=title,
                sheet_name=str(args.get("sheet_name") or "Sheet1"),
                headers=headers,
                rows=rows,
                credentials_json=credentials_json,
                refresh_token=refresh_token,
            )
            return ToolResult(kind="google_sheet", data={"action": "create", **data})
        except Exception as exc:
            return ToolResult.error(str(exc))

    def read_handler(args: dict[str, Any]) -> ToolResult:
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

    def write_handler(args: dict[str, Any]) -> ToolResult:
        if not google_libs_available():
            return _lib_error()
        spreadsheet_id = str(args.get("spreadsheet_id") or "").strip()
        range_a1 = str(args.get("range") or "").strip()
        if not spreadsheet_id or not range_a1:
            return ToolResult.error("spreadsheet_id and range are required.")
        try:
            rows = _parse_rows(args)
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

    def append_handler(args: dict[str, Any]) -> ToolResult:
        if not google_libs_available():
            return _lib_error()
        spreadsheet_id = str(args.get("spreadsheet_id") or "").strip()
        range_a1 = str(args.get("range") or "").strip()
        if not spreadsheet_id or not range_a1:
            return ToolResult.error("spreadsheet_id and range are required.")
        try:
            rows = _parse_rows(args)
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

    registry.register(GOOGLE_CREATE_SHEET, create_handler)
    registry.register(GOOGLE_READ_SHEET, read_handler)
    registry.register(GOOGLE_WRITE_SHEET, write_handler)
    registry.register(GOOGLE_APPEND_SHEET, append_handler)
