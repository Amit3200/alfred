"""Shared Google tool registration helpers."""

from __future__ import annotations

from backend.integrations.google.credentials import credentials_json_type
from backend.models.config import AlfredConfig


def google_credentials_ready(config: AlfredConfig) -> tuple[str, str] | None:
    """Return (credentials_json, refresh_token) when Google tools can register."""
    if not config.google.enabled:
        return None
    credentials_json = (config.google.credentials_json or "").strip()
    if not credentials_json:
        return None
    try:
        cred_type = credentials_json_type(credentials_json)
    except ValueError:
        return None
    refresh_token = (config.google.oauth_refresh_token or "").strip()
    if cred_type == "oauth_client" and not refresh_token:
        return None
    return credentials_json, refresh_token
