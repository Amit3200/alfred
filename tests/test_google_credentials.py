"""Tests for Google credential parsing."""

from __future__ import annotations

import json

import pytest

from backend.integrations.google.credentials import credentials_json_type, parse_oauth_client_config
from backend.integrations.google.oauth import begin_oauth, new_oauth_state, pop_oauth_session, pop_oauth_state


OAUTH_WEB = {
    "web": {
        "client_id": "123.apps.googleusercontent.com",
        "client_secret": "secret",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost:8080/callback"],
    }
}

SERVICE_ACCOUNT = {
    "type": "service_account",
    "project_id": "demo",
    "private_key_id": "key",
    "private_key": "-----BEGIN PRIVATE KEY-----\nMIIE\n-----END PRIVATE KEY-----\n",
    "client_email": "alfred@demo.iam.gserviceaccount.com",
    "client_id": "1",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
}


def test_credentials_json_type_oauth_web():
    assert credentials_json_type(json.dumps(OAUTH_WEB)) == "oauth_client"


def test_credentials_json_type_service_account():
    assert credentials_json_type(json.dumps(SERVICE_ACCOUNT)) == "service_account"


def test_parse_oauth_client_config_web():
    cfg = parse_oauth_client_config(json.dumps(OAUTH_WEB))
    assert cfg["client_id"].endswith(".apps.googleusercontent.com")


def test_credentials_json_type_invalid():
    with pytest.raises(ValueError, match="Unrecognized"):
        credentials_json_type('{"foo": "bar"}')


def test_oauth_state_roundtrip(tmp_path):
    state = new_oauth_state(tmp_path)
    assert pop_oauth_state(tmp_path, state) is True
    assert pop_oauth_state(tmp_path, state) is False


def test_oauth_session_stores_pkce_verifier(tmp_path):
    oauth_json = json.dumps(OAUTH_WEB)
    redirect = "http://127.0.0.1:8080/api/config/google/oauth/callback"
    state, url = begin_oauth(oauth_json, redirect_uri=redirect, data_dir=tmp_path)
    assert state in url
    session = pop_oauth_session(tmp_path, state)
    assert session is not None
    assert session["redirect_uri"] == redirect
    assert session["code_verifier"]
