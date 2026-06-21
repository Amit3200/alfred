"""Verify GitHub webhook signatures."""

from __future__ import annotations

import hashlib
import hmac


def verify_github_signature(body: bytes, header: str | None, secret: str) -> bool:
    if not secret:
        return False
    if not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    received = header.removeprefix("sha256=")
    return hmac.compare_digest(expected, received)
