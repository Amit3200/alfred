"""Register company script class tools."""

from __future__ import annotations

from pathlib import Path

from backend.models.config import AlfredConfig
from backend.tools.registry import ToolRegistry


def register_company_script_tools(
    registry: ToolRegistry,
    *,
    config: AlfredConfig,
    data_dir: Path | None,
) -> None:
    if not config.scripts.enabled:
        return
    from backend.tools.scripts.bundle import ScriptToolBundle

    registry.alfred_config = config
    if data_dir is not None:
        registry.data_dir = data_dir
    ScriptToolBundle().register(registry)
