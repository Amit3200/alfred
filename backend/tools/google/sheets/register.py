"""Register Google Sheets class tools."""

from __future__ import annotations

from backend.models.config import AlfredConfig
from backend.tools.registry import ToolRegistry


def register_sheet_tools(
    registry: ToolRegistry,
    *,
    credentials_json: str,
    refresh_token: str,
) -> None:
    from backend.tools.google.bundle import GoogleSheetToolBundle

    if getattr(registry, "alfred_config", None) is None:
        registry.alfred_config = AlfredConfig()
    GoogleSheetToolBundle().register(
        registry,
        extra={"credentials_json": credentials_json, "refresh_token": refresh_token},
    )
