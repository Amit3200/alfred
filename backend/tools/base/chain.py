"""Function chaining metadata for class-based tools.

Routing (L4) turns a ``ToolChain`` into a ``ToolPlan``. This module stays in L3.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.tools.base.tool import BaseTool


@dataclass(frozen=True)
class ToolChain:
    """Ordered tool names that implement a skill workflow."""

    name: str
    tools: tuple[str, ...]
    intent_class: str = ""
    goal: str = ""


def chain_from_tools(tools: list[BaseTool], *, start: str) -> list[str]:
    """Walk ``next_tools`` starting at ``start`` (stops on cycles)."""
    by_name = {tool.name: tool for tool in tools}
    ordered: list[str] = []
    seen: set[str] = set()
    current = start
    while current and current not in seen:
        seen.add(current)
        ordered.append(current)
        tool = by_name.get(current)
        nxt = tool.next_tools[0] if tool and tool.next_tools else ""
        current = nxt
    return ordered
