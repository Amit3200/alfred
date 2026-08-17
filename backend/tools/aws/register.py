"""Register AWS class tools."""

from __future__ import annotations

from backend.models.config import AlfredConfig
from backend.tools.registry import ToolRegistry


def register_aws_tools(registry: ToolRegistry, config: AlfredConfig) -> None:
    if not config.aws.enabled:
        return
    from backend.tools.aws.bundle import AwsToolBundle

    registry.alfred_config = config
    AwsToolBundle().register(registry)
