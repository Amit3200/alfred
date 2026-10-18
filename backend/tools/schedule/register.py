"""Register class-based schedule tools."""

from __future__ import annotations

from pathlib import Path

from backend.models.config import AlfredConfig
from backend.tools.registry import ToolRegistry
from backend.tools.schedule.bundle import ScheduleToolBundle
from backend.tools.schedule.tools import _schedule_playbook_frontmatter

__all__ = ["register_schedule_tools", "_schedule_playbook_frontmatter"]


def register_schedule_tools(registry: ToolRegistry, data_dir: Path | None) -> None:
    if data_dir is not None:
        registry.data_dir = data_dir
    if getattr(registry, "alfred_config", None) is None:
        registry.alfred_config = AlfredConfig()
    ScheduleToolBundle().register(registry)
