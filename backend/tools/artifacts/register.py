"""Register class-based HTML artifact tools."""

from __future__ import annotations

from pathlib import Path

from backend.models.config import AlfredConfig
from backend.tools.artifacts.bundle import ArtifactToolBundle
from backend.tools.registry import ToolRegistry


def register_artifact_tools(
    registry: ToolRegistry,
    *,
    config: AlfredConfig,
    data_dir: Path | None,
) -> None:
    if data_dir is None:
        return
    registry.alfred_config = config
    registry.data_dir = data_dir
    ArtifactToolBundle().register(registry)
