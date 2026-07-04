"""Build Google API credentials from Alfred secrets."""

from __future__ import annotations
import google.auth
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request


import json
from typing import Any

from backend.integrations.google.scopes import GOOGLE_SCOPES

GOOGLE_LIBS_HINT = "Install Google libraries: pip install 'alfred-agent[google]'"


def google_libs_available() -> bool:
    try:
        pass

        return True
    except ImportError:
        return False


def credentials_json_type(raw: str) -> str:
    """Return ``oauth_client``, ``service_account``, or raise."""
    data = json.loads(raw)
    if data.get("type") == "service_account":
        return "service_account"
    if "installed" in data or "web" in data or data.get("client_id"):
        return "oauth_client"
    raise ValueError(
        "Unrecognized Google credentials JSON. Paste an OAuth client or service account key."
    )


def parse_oauth_client_config(raw: str) -> dict[str, Any]:
    data = json.loads(raw)
    if "installed" in data:
        return data["installed"]
    if "web" in data:
        return data["web"]
    if data.get("client_id"):
        return data
    raise ValueError("OAuth client JSON must include client_id and client_secret.")


def build_google_credentials(
    *,
    credentials_json: str,
    refresh_token: str = "",
) -> Any:
    """Return google.auth credentials ready for API calls."""
    if not google_libs_available():
        raise RuntimeError(GOOGLE_LIBS_HINT)

    cred_type = credentials_json_type(credentials_json)
    if cred_type == "service_account":
        pass

        info = json.loads(credentials_json)
        return service_account.Credentials.from_service_account_info(info, scopes=GOOGLE_SCOPES)

    if not refresh_token.strip():
        raise RuntimeError(
            "Google OAuth refresh token missing. Save OAuth client JSON in Secrets, "
            "then click Connect Google in Integrations."
        )

    client = parse_oauth_client_config(credentials_json)
    client_id = str(client.get("client_id") or "")
    client_secret = str(client.get("client_secret") or "")
    token_uri = str(client.get("token_uri") or "https://oauth2.googleapis.com/token")
    if not client_id or not client_secret:
        raise RuntimeError("OAuth client JSON is missing client_id or client_secret.")

    pass

    return Credentials(
        token=None,
        refresh_token=refresh_token.strip(),
        token_uri=token_uri,
        client_id=client_id,
        client_secret=client_secret,
        scopes=GOOGLE_SCOPES,
    )


def refresh_if_needed(credentials: Any) -> Any:
    if not credentials.valid:
        pass

        credentials.refresh(Request())
    return credentials
