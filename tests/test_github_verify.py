"""Tests for GitHub webhook signature verification."""

from __future__ import annotations

import hashlib
import hmac

from backend.integrations.github.verify import verify_github_signature


def _sign(body: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def test_verify_github_signature_valid():
    body = b'{"zen":"Design for failure."}'
    secret = "test-secret"
    assert verify_github_signature(body, _sign(body, secret), secret) is True


def test_verify_github_signature_invalid():
    body = b'{"zen":"Design for failure."}'
    assert verify_github_signature(body, "sha256=deadbeef", "test-secret") is False


def test_verify_github_signature_missing_secret():
    body = b"{}"
    assert verify_github_signature(body, _sign(body, "x"), "") is False
