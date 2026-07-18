"""Helpers for lazy tool registration against a skill allowlist."""

from __future__ import annotations


def normalize_allowed(allowed_tools: list[str] | None) -> frozenset[str] | None:
    """``None`` means register all tools for enabled integrations."""
    if allowed_tools is None:
        return None
    cleaned = {name.strip() for name in allowed_tools if str(name).strip()}
    return frozenset(cleaned)


def wants_tool(name: str, allowed: frozenset[str] | None) -> bool:
    if allowed is None:
        return True
    return name in allowed


def wants_module(module_tools: frozenset[str], allowed: frozenset[str] | None) -> bool:
    if allowed is None:
        return True
    return bool(module_tools & allowed)
