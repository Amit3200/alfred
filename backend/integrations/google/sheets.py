"""Google Sheets read/write helpers."""

from __future__ import annotations
from googleapiclient.discovery import build


from typing import Any

from backend.integrations.google.credentials import build_google_credentials, refresh_if_needed


def _sheets_service(credentials_json: str, refresh_token: str):
    pass

    creds = build_google_credentials(
        credentials_json=credentials_json,
        refresh_token=refresh_token,
    )
    refresh_if_needed(creds)
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def read_sheet(
    *,
    spreadsheet_id: str,
    range_a1: str,
    credentials_json: str,
    refresh_token: str = "",
) -> dict[str, Any]:
    service = _sheets_service(credentials_json, refresh_token)
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=range_a1)
        .execute()
    )
    values = result.get("values") or []
    return {
        "spreadsheet_id": spreadsheet_id,
        "range": range_a1,
        "rows": values,
        "row_count": len(values),
    }


def write_sheet(
    *,
    spreadsheet_id: str,
    range_a1: str,
    values: list[list[Any]],
    credentials_json: str,
    refresh_token: str = "",
    value_input_option: str = "USER_ENTERED",
) -> dict[str, Any]:
    service = _sheets_service(credentials_json, refresh_token)
    body = {"values": values}
    result = (
        service.spreadsheets()
        .values()
        .update(
            spreadsheetId=spreadsheet_id,
            range=range_a1,
            valueInputOption=value_input_option,
            body=body,
        )
        .execute()
    )
    return {
        "spreadsheet_id": spreadsheet_id,
        "range": range_a1,
        "updated_cells": result.get("updatedCells", 0),
        "updated_rows": result.get("updatedRows", 0),
        "updated_columns": result.get("updatedColumns", 0),
    }


def append_sheet(
    *,
    spreadsheet_id: str,
    range_a1: str,
    values: list[list[Any]],
    credentials_json: str,
    refresh_token: str = "",
    value_input_option: str = "USER_ENTERED",
) -> dict[str, Any]:
    service = _sheets_service(credentials_json, refresh_token)
    body = {"values": values}
    result = (
        service.spreadsheets()
        .values()
        .append(
            spreadsheetId=spreadsheet_id,
            range=range_a1,
            valueInputOption=value_input_option,
            insertDataOption="INSERT_ROWS",
            body=body,
        )
        .execute()
    )
    updates = result.get("updates") or {}
    return {
        "spreadsheet_id": spreadsheet_id,
        "range": range_a1,
        "updated_cells": updates.get("updatedCells", 0),
        "updated_rows": updates.get("updatedRows", 0),
    }
