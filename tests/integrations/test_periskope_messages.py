"""Periskope message download uses the documented date-filter endpoint."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from backend.integrations.periskope.api import PeriskopeApiClient
from backend.integrations.periskope.connector import PeriskopeConnector, _normalize_message
from backend.integrations.periskope.time_range import resolve_message_window
from backend.models.config import AlfredConfig, ConnectorsConfig, PeriskopeConfig
from backend.models.task import Task
from backend.routing.connector_intent import build_connector_tool_plan
from backend.tools.base.tool import ToolContext
from backend.tools.connectors.tools import connector_get_messages


def test_org_phone_strips_whatsapp_suffix():
    client = PeriskopeApiClient(api_token="tok", org_phone="+91 98765 43210@c.us")
    assert client.org_phone == "919876543210"


def test_list_messages_with_dates_hits_org_wide_endpoint(monkeypatch):
    captured: dict[str, object] = {}

    def fake_request(self, method, path, *, params=None, json_body=None, timeout=None):
        captured.update({"method": method, "path": path, "params": params, "timeout": timeout})
        return {"messages": []}

    monkeypatch.setattr(PeriskopeApiClient, "request", fake_request)
    client = PeriskopeApiClient(api_token="tok", org_phone="9198")
    client.list_messages(chat_id="1203@g.us", start_time="2026-08-22", end_time="2026-08-22")
    assert captured["path"] == "/chats/messages"
    assert captured["params"]["start_time"] == "2026-08-22"
    assert captured["params"]["end_time"] == "2026-08-22"


def test_list_messages_per_chat_without_dates(monkeypatch):
    captured: dict[str, object] = {}

    def fake_request(self, method, path, *, params=None, json_body=None, timeout=None):
        captured.update({"path": path, "params": params})
        return {"messages": []}

    monkeypatch.setattr(PeriskopeApiClient, "request", fake_request)
    client = PeriskopeApiClient(api_token="tok")
    client.list_messages(chat_id="12036329726967XXXX@g.us")
    assert captured["path"] == "/chats/12036329726967XXXX@g.us/messages"
    assert "start_time" not in captured["params"]


def test_normalize_message_uses_sender_phone():
    row = _normalize_message(
        {
            "message_id": "m1",
            "chat_id": "1203@g.us",
            "body": "hello",
            "sender_phone": "9198@c.us",
            "timestamp": "2026-08-22 10:00:00+00",
        }
    )
    assert row["sender_name"] == "9198@c.us"
    assert row["body"] == "hello"


def test_resolve_22nd_august_window():
    now = datetime(2026, 8, 23, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    start, end = resolve_message_window(intent="22nd August so far", now=now)
    assert start.startswith("2026-08-22T00:00:00")
    assert end.startswith("2026-08-22T23:59:59")


def test_resolve_last_week_window():
    now = datetime(2026, 8, 23, 23, 30, tzinfo=ZoneInfo("Asia/Kolkata"))
    start, end = resolve_message_window(intent="from last 1 week", now=now)
    assert start.startswith("2026-08-16T00:00:00")
    assert end.startswith("2026-08-23T23:30:00")


def test_summarize_plan_uses_get_messages():
    task = Task(
        source="ui",
        user_id="U1",
        channel_id="C1",
        thread_ts="1.0",
        raw_text="@alfred list Periskope WhatsApp chats for 22nd August so far and summarise them for each channel",
        cleaned_intent="list Periskope WhatsApp chats for 22nd August so far and summarise them for each channel",
    )
    plan = build_connector_tool_plan(task)
    assert plan is not None
    assert "connector_get_messages" in plan.tools_needed
    step = plan.steps[0]
    assert step.tool == "connector_get_messages"
    assert "2026-08-22" in str(step.args_hint.get("start_time") or "")


def test_connector_get_messages_allows_missing_chat_id(monkeypatch):
    config = AlfredConfig(
        connectors=ConnectorsConfig(periskope=PeriskopeConfig(enabled=True, org_phone="9198", api_token="tok")),
    )

    def fake_list(self, cfg, *, chat_id="", start_time="", end_time="", limit=100, intent=""):
        return [
            {
                "message_id": "m1",
                "chat_id": "1203@g.us",
                "sender_name": "Riya",
                "body": "COD failed",
                "timestamp": "2026-08-22 09:00:00+00",
            }
        ]

    monkeypatch.setattr(PeriskopeConnector, "list_messages", fake_list)
    result = connector_get_messages(
        ToolContext(config=config),
        {"start_time": "2026-08-22", "end_time": "2026-08-22"},
    )
    assert result.kind == "connector_messages"
    assert result.data["chat_count"] == 1
    assert result.data["chats"][0]["chat_id"] == "1203@g.us"


def test_list_messages_paginates_date_window(monkeypatch):
    calls: list[dict[str, object]] = []

    def fake_request(self, method, path, *, params=None, json_body=None, timeout=None):
        offset = int((params or {}).get("offset") or 0)
        calls.append({"path": path, "offset": offset})
        if offset == 0:
            return {
                "messages": [
                    {"message_id": "m1", "chat_id": "a@g.us", "body": "one", "sender_phone": "1"}
                    for _ in range(200)
                ]
            }
        return {
            "messages": [
                {"message_id": "m2", "chat_id": "b@g.us", "body": "two", "sender_phone": "2"}
            ]
        }

    monkeypatch.setattr(PeriskopeApiClient, "request", fake_request)
    config = AlfredConfig(
        connectors=ConnectorsConfig(periskope=PeriskopeConfig(enabled=True, org_phone="9198", api_token="tok")),
    )
    rows = PeriskopeConnector().list_messages(
        config,
        start_time="2026-08-22",
        end_time="2026-08-22",
        limit=500,
    )
    assert [c["path"] for c in calls] == ["/chats/messages", "/chats/messages"]
    assert calls[1]["offset"] == 200
    assert len(rows) == 201


def test_connector_sends_end_of_day_iso_window(monkeypatch):
    captured: dict[str, object] = {}

    def fake_request(self, method, path, *, params=None, json_body=None, timeout=None):
        captured["params"] = params
        return {"messages": []}

    monkeypatch.setattr(PeriskopeApiClient, "request", fake_request)
    config = AlfredConfig(
        connectors=ConnectorsConfig(periskope=PeriskopeConfig(enabled=True, org_phone="9198", api_token="tok")),
    )
    PeriskopeConnector().list_messages(
        config,
        start_time="2026-08-21",
        end_time="2026-08-21",
    )
    params = captured["params"]
    assert isinstance(params, dict)
    assert str(params["start_time"]).startswith("2026-08-21T00:00:00")
    assert str(params["end_time"]).startswith("2026-08-21T23:59:59")


def test_enrich_ticket_appends_last_chat_messages(monkeypatch):
    from backend.integrations.platform.types import ExternalEntity

    config = AlfredConfig(
        connectors=ConnectorsConfig(periskope=PeriskopeConfig(enabled=True, org_phone="9198", api_token="tok")),
    )

    def fake_get_ticket(self, ticket_id: str):
        return {
            "ticket": {"ticket_id": ticket_id, "subject": "COD disable reason", "status": "open", "priority": 2},
            "chat": {"chat_id": "1203@g.us", "chat_name": "Nmpc"},
        }

    def fake_list(self, cfg, *, chat_id="", start_time="", end_time="", limit=100, intent=""):
        assert chat_id == "1203@g.us"
        assert limit == 20
        return [
            {"sender_name": "Riya", "body": "newer", "timestamp": "t2"},
            {"sender_name": "Merchant", "body": "older", "timestamp": "t1"},
        ]

    monkeypatch.setattr(PeriskopeApiClient, "get_ticket", fake_get_ticket)
    monkeypatch.setattr(PeriskopeConnector, "list_messages", fake_list)
    entity = ExternalEntity(
        connector_id="periskope",
        kind="ticket",
        external_id="BKT-9",
        title="COD disable reason",
        chat_id="1203@g.us",
    )
    enriched = PeriskopeConnector().enrich(config, entity)
    assert "Recent WhatsApp messages:" in enriched.description
    assert enriched.description.index("older") < enriched.description.index("newer")
    assert "Merchant" in enriched.description

