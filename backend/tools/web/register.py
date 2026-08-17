"""Register web search class tools."""

from __future__ import annotations

from backend.models.config import AlfredConfig
from backend.tools.registry import ToolRegistry


def register_web_search_tools(registry: ToolRegistry, config: AlfredConfig) -> None:
    if not config.web_search.enabled:
        return
    from backend.tools.web.bundle import WebToolBundle

    registry.alfred_config = config
    WebToolBundle().register(registry)
