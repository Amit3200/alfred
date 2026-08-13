"""Public URL helpers for HTML artifacts."""

from __future__ import annotations


def artifact_public_url(public_base_url: str, path: str) -> str:
    """Join configured public base with an artifact path."""
    base = (public_base_url or "").strip().rstrip("/")
    normalized = path if path.startswith("/") else f"/{path}"
    if not base:
        return normalized
    return f"{base}{normalized}"
