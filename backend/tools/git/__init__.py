"""Register all git-domain tools (API, local mirror, write, Graphify)."""

from __future__ import annotations

from pathlib import Path

from backend.models.config import AlfredConfig
from backend.tools.catalog import GIT_API_TOOLS, GIT_LOCAL_TOOLS, GIT_WRITE_TOOLS, GRAPHIFY_TOOLS
from backend.tools.git.api import register_git_api_tools
from backend.tools.git.graphify import register_graphify_tools
from backend.tools.git.local import register_local_git_tools
from backend.tools.git.write import register_git_write_tools
from backend.tools.registry import ToolRegistry
from backend.tools.selection import wants_module


def register_git_tools(
    registry: ToolRegistry,
    config: AlfredConfig,
    *,
    data_dir: Path | None = None,
) -> None:
    if not config.git.enabled:
        return
    allowed = registry._registration_filter
    if wants_module(GIT_API_TOOLS, allowed):
        register_git_api_tools(registry, config)
    if data_dir is None:
        return
    path = Path(data_dir)
    if wants_module(GIT_LOCAL_TOOLS, allowed):
        register_local_git_tools(registry, config=config, data_dir=path)
    if config.git.write_enabled and wants_module(GIT_WRITE_TOOLS, allowed):
        register_git_write_tools(registry, config=config, data_dir=path)
    if wants_module(GRAPHIFY_TOOLS, allowed):
        register_graphify_tools(registry, config=config, data_dir=path)
