"""HMAC helpers for inbound connector webhooks."""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any


def hmac_sha256_hex(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def signatures_match(expected: str, received: str) -> bool:
    if not expected or not received:
        return False
    return hmac.compare_digest(expected, received)


def verify_hmac_sha256(
    *,
    secret: str,
    body: bytes,
    signature: str,
    payload: dict[str, Any] | None = None,
) -> bool:
    """Accept HMAC of raw body, or compact JSON (JS JSON.stringify-style)."""
    secret = (secret or "").strip()
    signature = (signature or "").strip()
    if not secret or not signature:
        return False
    if signatures_match(hmac_sha256_hex(secret, body), signature):
        return True
    if payload is None:
        return False
    compact = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return signatures_match(hmac_sha256_hex(secret, compact), signature)
