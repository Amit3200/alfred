"""Map connector secrets on AlfredSecrets.connectors ↔ config.connectors.*.api_token."""

from __future__ import annotations

from typing import Any

from backend.models.config import AlfredConfig, AlfredSecrets

_SECRET_FIELDS = ("api_token", "webhook_secret")


def _connector_instances(config: AlfredConfig) -> list[tuple[str, Any]]:
    connectors = getattr(config, "connectors", None)
    if connectors is None:
        return []
    out: list[tuple[str, Any]] = []
    fields = getattr(type(connectors), "model_fields", {})
    for name in fields:
        instance = getattr(connectors, name, None)
        if instance is not None:
            out.append((name, instance))
    return out


def apply_connector_secrets(config: AlfredConfig, secrets_obj: AlfredSecrets) -> None:
    stored = dict(secrets_obj.connectors or {})
    for name, instance in _connector_instances(config):
        blob = stored.get(name) if isinstance(stored.get(name), dict) else {}
        for field in _SECRET_FIELDS:
            if not hasattr(instance, field):
                continue
            value = str((blob or {}).get(field) or getattr(instance, field) or "")
            setattr(instance, field, value)


def extract_connector_secrets(config: AlfredConfig, secrets_obj: AlfredSecrets) -> None:
    current = dict(secrets_obj.connectors or {})
    for name, instance in _connector_instances(config):
        blob = dict(current.get(name) or {})
        for field in _SECRET_FIELDS:
            if not hasattr(instance, field):
                continue
            value = str(getattr(instance, field) or "").strip()
            if value:
                blob[field] = value
            setattr(instance, field, "")
        if blob:
            current[name] = blob
    secrets_obj.connectors = current


def connector_secrets_status(secrets_obj: AlfredSecrets) -> dict[str, dict[str, bool]]:
    out: dict[str, dict[str, bool]] = {}
    for name, blob in (secrets_obj.connectors or {}).items():
        if not isinstance(blob, dict):
            continue
        out[str(name)] = {str(key): bool(str(value or "").strip()) for key, value in blob.items()}
    return out


def merge_connector_secret_payload(
    secrets_obj: AlfredSecrets,
    incoming: dict[str, dict[str, str]] | None,
) -> None:
    if not incoming:
        return
    current = dict(secrets_obj.connectors or {})
    for name, blob in incoming.items():
        if not isinstance(blob, dict):
            continue
        stored = dict(current.get(name) or {})
        for key, value in blob.items():
            text = str(value or "").strip()
            if text:
                stored[str(key)] = text
        if stored:
            current[str(name)] = stored
    secrets_obj.connectors = current
