"""Google OAuth connect flow for admin UI."""

from __future__ import annotations

import json
import os
import secrets
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from backend.google.credentials import parse_oauth_client_config
from backend.google.scopes import GOOGLE_SCOPES

_STATE_TTL_SECONDS = 600


@contextmanager
def _relax_oauth_scope_check():
    """Google may return openid/profile scopes beyond the strict oauthlib check."""
    previous = os.environ.get("OAUTHLIB_RELAX_TOKEN_SCOPE")
    os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("OAUTHLIB_RELAX_TOKEN_SCOPE", None)
        else:
            os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = previous


def oauth_state_path(data_dir: Path) -> Path:
    return data_dir / "google_oauth_state.json"


def _write_oauth_state(data_dir: Path, payload: dict[str, Any]) -> None:
    path = oauth_state_path(data_dir)
    path.write_text(json.dumps(payload), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _build_flow(credentials_json: str, *, redirect_uri: str):
    from google_auth_oauthlib.flow import Flow

    client = parse_oauth_client_config(credentials_json)
    config = {
        "web": {
            "client_id": client["client_id"],
            "client_secret": client["client_secret"],
            "auth_uri": client.get("auth_uri", "https://accounts.google.com/o/oauth2/auth"),
            "token_uri": client.get("token_uri", "https://oauth2.googleapis.com/token"),
            "redirect_uris": [redirect_uri],
        }
    }
    return Flow.from_client_config(config, scopes=GOOGLE_SCOPES, redirect_uri=redirect_uri)


def begin_oauth(
    credentials_json: str,
    *,
    redirect_uri: str,
    data_dir: Path,
) -> tuple[str, str]:
    """Start OAuth; return ``(state, authorization_url)`` and persist PKCE verifier."""
    state = secrets.token_urlsafe(24)
    flow = _build_flow(credentials_json, redirect_uri=redirect_uri)
    url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        state=state,
    )
    _write_oauth_state(
        data_dir,
        {
            "state": state,
            "created_at": time.time(),
            "redirect_uri": redirect_uri,
            "code_verifier": flow.code_verifier,
        },
    )
    return state, url


def pop_oauth_session(data_dir: Path, state: str) -> dict[str, Any] | None:
    """Validate and consume a pending OAuth session (includes PKCE verifier)."""
    path = oauth_state_path(data_dir)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        path.unlink(missing_ok=True)
        return None
    path.unlink(missing_ok=True)
    if payload.get("state") != state:
        return None
    created = float(payload.get("created_at") or 0)
    if (time.time() - created) > _STATE_TTL_SECONDS:
        return None
    redirect_uri = str(payload.get("redirect_uri") or "").strip()
    if not redirect_uri:
        return None
    return {
        "redirect_uri": redirect_uri,
        "code_verifier": payload.get("code_verifier"),
    }


def finish_oauth(
    credentials_json: str,
    *,
    code: str,
    redirect_uri: str,
    code_verifier: str | None,
) -> dict[str, Any]:
    """Exchange authorization code for tokens using the stored PKCE verifier."""
    flow = _build_flow(credentials_json, redirect_uri=redirect_uri)
    if code_verifier:
        flow.code_verifier = code_verifier
    with _relax_oauth_scope_check():
        flow.fetch_token(code=code)
    creds = flow.credentials
    if not creds.refresh_token:
        raise RuntimeError(
            "Google did not return a refresh token. Revoke Alfred access in your Google "
            "Account and connect again (prompt=consent)."
        )
    return {
        "refresh_token": creds.refresh_token,
        "scopes": list(creds.scopes or []),
    }


# Backwards-compatible helpers for tests
def new_oauth_state(data_dir: Path) -> str:
    state = secrets.token_urlsafe(24)
    _write_oauth_state(data_dir, {"state": state, "created_at": time.time()})
    return state


def pop_oauth_state(data_dir: Path, state: str) -> bool:
    """Legacy boolean check for minimal OAuth state files (tests)."""
    path = oauth_state_path(data_dir)
    if not path.is_file():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        path.unlink(missing_ok=True)
        return False
    path.unlink(missing_ok=True)
    if payload.get("state") != state:
        return False
    created = float(payload.get("created_at") or 0)
    return (time.time() - created) <= _STATE_TTL_SECONDS


def authorization_url(
    credentials_json: str,
    *,
    redirect_uri: str,
    state: str,
    data_dir: Path | None = None,
) -> str:
    if data_dir is not None:
        _, url = begin_oauth(credentials_json, redirect_uri=redirect_uri, data_dir=data_dir)
        return url
    flow = _build_flow(credentials_json, redirect_uri=redirect_uri)
    url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        state=state,
    )
    return url


def exchange_code(
    credentials_json: str,
    *,
    redirect_uri: str,
    code: str,
    code_verifier: str | None = None,
) -> dict[str, Any]:
    return finish_oauth(
        credentials_json,
        code=code,
        redirect_uri=redirect_uri,
        code_verifier=code_verifier,
    )
