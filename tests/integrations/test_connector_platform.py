"""Connector platform HMAC and Periskope webhook normalization."""

from __future__ import annotations

import json

from backend.integrations.periskope.normalize import entity_from_ticket, parse_webhook_body
from backend.integrations.platform.hmac import hmac_sha256_hex, verify_hmac_sha256
from backend.integrations.platform.store import ConnectorSyncStore


def test_hmac_accepts_raw_body():
    body = b'{"event_type":"ticket.created"}'
    secret = "s3cret"
    signature = hmac_sha256_hex(secret, body)
    assert verify_hmac_sha256(secret=secret, body=body, signature=signature)


def test_hmac_accepts_compact_json():
    payload = {"event_type": "ticket.created", "data": {"ticket_id": "T-1"}}
    body = json.dumps(payload).encode("utf-8")
    compact = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    secret = "s3cret"
    signature = hmac_sha256_hex(secret, compact)
    assert verify_hmac_sha256(secret=secret, body=body, signature=signature, payload=payload)


def test_ticket_entity_from_periskope_payload():
    entity = entity_from_ticket(
        {
            "chat": {"chat_id": "1203@g.us", "chat_name": "Everaw"},
            "ticket": {
                "ticket_id": "BKT-001",
                "subject": "COD failing",
                "status": "open",
                "priority": 3,
                "assignee": "azeem@example.com",
                "ticket_labels": "p0, checkout",
            },
            "message": {"body": "customer cannot pay"},
        }
    )
    assert entity is not None
    assert entity.external_id == "BKT-001"
    assert entity.title == "COD failing"
    assert entity.priority == "High"
    assert entity.chat_id == "1203@g.us"
    assert "customer cannot pay" in entity.description
    assert entity.mapping_key() == "periskope:ticket:BKT-001"


def test_parse_webhook_ignores_message_created():
    body = json.dumps(
        {
            "event_type": "message.created",
            "data": {"body": "hello", "chat_id": "1203@g.us"},
        }
    ).encode("utf-8")
    events = parse_webhook_body(body)
    assert len(events) == 1
    assert events[0].entity is None


def test_parse_webhook_ticket_created():
    body = json.dumps(
        {
            "event_type": "ticket.created",
            "data": {
                "ticket": {"ticket_id": "BKT-002", "subject": "UPI intent", "priority": 2, "status": "open"},
            },
        }
    ).encode("utf-8")
    events = parse_webhook_body(body)
    assert events[0].entity is not None
    assert events[0].entity.title == "UPI intent"
    assert events[0].needs_enrich is True


def test_connector_sync_store_roundtrip(tmp_path):
    store = ConnectorSyncStore(tmp_path)
    store.put("periskope:ticket:BKT-001", {"slack_record_id": "Rec123", "jira_key": "TS-9"})
    row = store.get("periskope:ticket:BKT-001")
    assert row is not None
    assert row["slack_record_id"] == "Rec123"
    assert row["jira_key"] == "TS-9"


def test_webhook_rejects_unknown_connector_and_bad_signature(tmp_path):
    from backend.config_manager import ConfigManager
    from backend.integrations.platform.webhook import process_connector_webhook

    manager = ConfigManager(tmp_path / "alfred")
    manager.init()
    unknown = process_connector_webhook(
        "missing",
        headers={},
        body=b"{}",
        manager=manager,
    )
    assert unknown["status_code"] == 404

    config, secrets = manager.load_merged()
    config.connectors.periskope.enabled = True
    secrets.connectors = {"periskope": {"api_token": "tok", "webhook_secret": "hook"}}
    manager.save_merged(config, secrets)

    bad = process_connector_webhook(
        "periskope",
        headers={"x-periskope-signature": "deadbeef"},
        body=b'{"event_type":"ticket.created"}',
        manager=manager,
    )
    assert bad["status_code"] == 401

    payload = {"event_type": "message.created", "data": {"body": "hi"}}
    raw = json.dumps(payload).encode("utf-8")
    ok = process_connector_webhook(
        "periskope",
        headers={"x-periskope-signature": hmac_sha256_hex("hook", raw)},
        body=raw,
        manager=manager,
    )
    assert ok["ok"] is True
    assert ok["applied"] == 0


def test_connector_tools_register_when_enabled():
    from backend.models.config import AlfredConfig, ConnectorsConfig, PeriskopeConfig
    from backend.tools.builder import build_tool_registry

    config = AlfredConfig(
        connectors=ConnectorsConfig(periskope=PeriskopeConfig(enabled=True, org_phone="9198")),
    )
    registry = build_tool_registry(config)
    assert "connector_list_tickets" in registry._tools
    assert "connector_get_messages" in registry._tools
    assert "connector_poll" in registry._tools


def test_connector_tools_register_when_disabled():
    from backend.models.config import AlfredConfig
    from backend.tools.builder import build_tool_registry

    registry = build_tool_registry(AlfredConfig(), allowed_tools=["connector_list_chats"])
    assert "connector_list_chats" in registry._tools


def test_poll_preview_does_not_replicate(tmp_path, monkeypatch):
    from backend.integrations.platform.poll import poll_connector
    from backend.integrations.platform.types import ExternalEntity
    from backend.models.config import AlfredConfig
    from unittest.mock import MagicMock

    entity = ExternalEntity(
        connector_id="periskope",
        kind="ticket",
        external_id="BKT-1",
        title="COD failing",
    )
    fake = MagicMock()
    fake.enabled.return_value = True
    fake.accepts.return_value = True
    fake.list_tickets.return_value = [entity]
    fake.list_tasks.return_value = []
    fake.replica_targets.return_value = ("slack_board",)

    monkeypatch.setattr("backend.integrations.platform.poll.get_connector", lambda _id: fake)
    called = {"apply": 0}

    def _boom(*_args, **_kwargs):
        called["apply"] += 1
        raise AssertionError("preview must not replicate")

    monkeypatch.setattr("backend.integrations.platform.poll.apply_entity", _boom)
    result = poll_connector("periskope", AlfredConfig(), data_dir=tmp_path, replicate=False)
    assert result["ok"] is True
    assert result["preview"]["ticket_count"] == 1
    assert result["applied"] == 0
    assert called["apply"] == 0


def test_poll_replicate_calls_apply_entity(tmp_path, monkeypatch):
    from backend.integrations.platform.poll import poll_connector
    from backend.integrations.platform.types import ExternalEntity
    from backend.models.config import AlfredConfig
    from unittest.mock import MagicMock

    entity = ExternalEntity(
        connector_id="periskope",
        kind="ticket",
        external_id="BKT-2",
        title="Refund delay",
    )
    fake = MagicMock()
    fake.enabled.return_value = True
    fake.accepts.return_value = True
    fake.list_tickets.return_value = [entity]
    fake.list_tasks.return_value = []
    fake.replica_targets.return_value = ("slack_board",)

    monkeypatch.setattr("backend.integrations.platform.poll.get_connector", lambda _id: fake)
    applied = []

    def _apply(ent, config, *, data_dir, targets):
        applied.append((ent.external_id, targets))
        return {"ok": True, "targets": {"slack_board": {"status": "created"}}}

    monkeypatch.setattr("backend.integrations.platform.poll.apply_entity", _apply)
    result = poll_connector("periskope", AlfredConfig(), data_dir=tmp_path, replicate=True)
    assert result["ok"] is True
    assert result["created"] == 1
    assert applied == [("BKT-2", ("slack_board",))]
