"""Register inbound connector tools when the connector module is in scope."""

from __future__ import annotations

from backend.models.config import AlfredConfig
from backend.tools.connectors.bundle import ConnectorToolBundle
from backend.tools.registry import ToolRegistry


def register_connector_tools(registry: ToolRegistry, config: AlfredConfig) -> None:
    # Register even when disabled so chat can call the tool and get a clear
    # "enable in Integrations" error instead of "I have no tool".
    registry.alfred_config = config
    ConnectorToolBundle().register(registry)
