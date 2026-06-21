"""GitHub REST helpers for Alfred ingress."""

from __future__ import annotations

import logging
from typing import Any

import requests

from backend.git.api import GitApiClient
from backend.models.config import AlfredConfig

logger = logging.getLogger(__name__)

# GitHub issue-comment reactions API supports: +1, -1, laugh, confused, heart, hooray, rocket, eyes
REACTION_ACK = "eyes"
REACTION_DONE = "+1"  # 👍 — closest API equivalent to a done/tick ack (no ✅ in GitHub reactions API)
REACTION_FAILED = "confused"


def post_pull_request_comment(
    config: AlfredConfig,
    *,
    repo: str,
    number: int,
    body: str,
) -> dict[str, Any]:
    if not config.git.enabled or not config.git.token:
        raise RuntimeError("Git token is not configured — cannot post PR comments.")
    client = GitApiClient.from_alfred_config(config)
    return client.create_issue_comment(repo, number, body)


def react_to_issue_comment(
    config: AlfredConfig,
    *,
    repo: str,
    comment_id: int,
    content: str,
) -> dict[str, Any]:
    if not config.git.enabled or not config.git.token:
        raise RuntimeError("Git token is not configured — cannot react to PR comments.")
    if config.git.provider != "github":
        return {}
    client = GitApiClient.from_alfred_config(config)
    return client.create_issue_comment_reaction(repo, comment_id, content)


def exchange_oauth_code(
    *,
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
) -> dict[str, Any]:
    response = requests.post(
        "https://github.com/login/oauth/access_token",
        headers={"Accept": "application/json"},
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
        },
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("error"):
        raise RuntimeError(str(payload.get("error_description") or payload.get("error")))
    return payload
