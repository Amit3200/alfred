"""Built-in connector registry."""

from __future__ import annotations

from backend.integrations.platform.connector import Connector

_CONNECTORS: dict[str, Connector] | None = None


def _load() -> dict[str, Connector]:
    from backend.integrations.periskope.connector import PeriskopeConnector

    return {
        PeriskopeConnector.id: PeriskopeConnector(),
    }


def connector_registry() -> dict[str, Connector]:
    global _CONNECTORS
    if _CONNECTORS is None:
        _CONNECTORS = _load()
    return _CONNECTORS


def get_connector(connector_id: str) -> Connector | None:
    return connector_registry().get((connector_id or "").strip().lower())


def list_connector_ids() -> list[str]:
    return sorted(connector_registry())
