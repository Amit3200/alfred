"""Tests for HTML deck extraction and save tool."""

from __future__ import annotations

from backend.formatting.file_exports import extract_html_deck, prepare_slack_delivery
from backend.tools.artifacts_tool import register_artifact_tools
from backend.tools.registry import ToolRegistry

from tests.slide_fixtures import MINIMAL_SLIDE_HTML

SAMPLE = MINIMAL_SLIDE_HTML


def test_extract_html_deck_from_fence():
    text = f"Here is your deck:\n\n```html\n{SAMPLE}\n```\n"
    result = extract_html_deck(text)
    assert result is not None
    html, filename = result
    assert "Checkout Redirect" in html
    assert filename == "checkout-redirect.html"


def test_extract_html_deck_raw():
    result = extract_html_deck(SAMPLE)
    assert result is not None
    assert result[0].startswith("<!DOCTYPE html>")


def test_prepare_slack_delivery_attaches_html_not_publish_note():
    text = f"```html\n{SAMPLE}\n```"
    delivery = prepare_slack_delivery(text, "create html slides from metrics")
    assert delivery.files
    assert delivery.files[0].mime_type == "text/html"
    assert delivery.files[0].filename == "checkout-redirect.html"
    assert "Not published" in delivery.text


def test_prepare_slack_delivery_html_when_publish_intent():
    delivery = prepare_slack_delivery(SAMPLE, "publish slides to redirection-2025")
    assert delivery.files
    assert "Not published" not in delivery.text


def test_prepare_slack_delivery_skips_attach_when_tool_already_saved():
    delivery = prepare_slack_delivery(
        "*HTML slide deck saved* (not published to a share URL).\n"
        f"File: `deck.html`\n\n```html\n{SAMPLE}\n```",
        "create html slides",
    )
    assert not delivery.files
    assert "HTML slide deck saved" in delivery.text


def test_save_html_deck_tool(tmp_path):
    from backend.config_manager import ConfigManager

    manager = ConfigManager(tmp_path)
    manager.init()
    config, _ = manager.load_merged()
    registry = ToolRegistry()
    register_artifact_tools(registry, config=config, data_dir=tmp_path)
    result = registry.run(
        "save_html_deck",
        {"html": SAMPLE, "filename": "metrics.html"},
        allowed=["save_html_deck", "publish_html_artifact"],
    )
    assert result.kind == "html_deck_saved"
    assert result.data["filename"] == "metrics.html"
    saved = tmp_path / "exports" / "metrics.html"
    assert saved.is_file()
    assert "Checkout Redirect" in saved.read_text(encoding="utf-8")


def test_save_html_deck_reuses_filename_on_retry(tmp_path):
    import json

    from backend.config_manager import ConfigManager

    manager = ConfigManager(tmp_path)
    manager.init()
    config, _ = manager.load_merged()
    registry = ToolRegistry()
    register_artifact_tools(registry, config=config, data_dir=tmp_path)
    first = registry.run(
        "save_html_deck",
        {"html": SAMPLE},
        allowed=["save_html_deck", "publish_html_artifact"],
    )
    registry.tool_trace.append(
        {
            "tool": "save_html_deck",
            "success": True,
            "observation": json.dumps({"kind": "html_deck_saved", "data": first.data}),
        }
    )
    second = registry.run(
        "save_html_deck",
        {"html": SAMPLE.replace("Checkout Redirect", "Checkout Redirect v2")},
        allowed=["save_html_deck", "publish_html_artifact"],
    )
    assert second.data["filename"] == first.data["filename"]
    export_dir = tmp_path / "exports"
    assert len(list(export_dir.glob("*.html"))) == 1
