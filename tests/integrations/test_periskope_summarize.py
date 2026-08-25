"""WhatsApp ticket intake: ignore dumps, summarize problem + actions."""

from __future__ import annotations

from backend.integrations.periskope.summarize import (
    heuristic_intake,
    is_noise_text,
    looks_like_ticket_id,
    summarize_ticket,
)
from backend.integrations.platform.types import ExternalEntity
from backend.models.config import AlfredConfig


def test_looks_like_ticket_id_rejects_whatsapp_dump():
    dump = "{'from_me': True, 'id': '3EB060A3EBC140239A7A57', 'remote': '120363410912716439@g.us'}"
    assert not looks_like_ticket_id(dump)
    assert not looks_like_ticket_id({"from_me": True, "id": "3EB060A3EBC140239A7A57"})
    assert not looks_like_ticket_id("3EB060A3EBC140239A7A57")
    assert looks_like_ticket_id("FLE-027")
    assert looks_like_ticket_id("BKT-001")


def test_heuristic_intake_ignores_away_and_reminder_noise():
    entity = ExternalEntity(
        connector_id="periskope",
        kind="ticket",
        external_id="FLE-027",
        title="Test 06",
        chat_name="FP - Periskope testing group",
    )
    recent = [
        {
            "sender_name": "api",
            "body": "Friendly reminder: outstanding balance of ₹1935.51 for your FlexyPe account",
        },
        {
            "sender_name": "916265673155@c.us",
            "body": "Hello! Thanks for reaching out! Your message is important to us! Please note that our business hours are from Monday to Saturday",
        },
        {"sender_name": "Merchant", "body": "COD is failing on checkout for Test 06", "from_me": False},
        {"sender_name": "rules-bot-no-flag", "body": "Hello! Thanks for reaching out!"},
    ]
    assert is_noise_text(recent[0]["body"], sender="api")
    intake = heuristic_intake(entity, recent)
    assert intake.title == "Test 06"
    assert "COD is failing" in intake.problem
    assert "outstanding balance" not in intake.problem
    assert intake.action_items
    assert "Investigate" in intake.action_items[0]


def test_summarize_ticket_falls_back_when_llm_missing(monkeypatch):
    monkeypatch.setattr(
        "backend.integrations.periskope.summarize.llm_intake",
        lambda *_args, **_kwargs: None,
    )
    entity = ExternalEntity(
        connector_id="periskope",
        kind="ticket",
        external_id="FLE-027",
        title="UPI timeout",
        chat_name="billing",
    )
    intake = summarize_ticket(
        AlfredConfig(),
        entity,
        [{"sender_name": "Riya", "body": "UPI intent stuck after collect", "from_me": False}],
    )
    assert "UPI" in intake.title or "UPI" in intake.problem
    assert intake.action_items
