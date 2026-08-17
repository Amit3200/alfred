"""Alfred tools — domain packages plus a shared registry builder.

Import ``build_tool_registry`` from ``backend.tools.builder`` (or lazily via
``backend.tools.build_tool_registry``) so this package init stays import-safe.
"""

from __future__ import annotations

from typing import Any

__all__ = ["build_tool_registry", "build_git_tool_registry"]


def __getattr__(name: str) -> Any:
    if name in {"build_tool_registry", "build_git_tool_registry"}:
        from backend.tools.builder import build_git_tool_registry, build_tool_registry

        return build_tool_registry if name == "build_tool_registry" else build_git_tool_registry
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
