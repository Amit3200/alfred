"""Tests for Slack file exports and table formatting."""

from __future__ import annotations

from backend.ingress.file_exports import (
    build_export_attachment,
    detect_export_format,
    extract_tabular_data,
    prepare_slack_delivery,
)
from backend.ingress.slack_format import format_for_slack


def test_detect_export_format_csv():
    assert detect_export_format("can you give me a csv of it?") == "csv"


def test_detect_export_format_json():
    assert detect_export_format("export this as json") == "json"


def test_extract_tabular_data_from_csv_fence():
    text = """Here's the data:

```
Merchant,Error,Count
thejanki.com,Shopify API Failed,18
THE GIR FARMER,invalid API key,17
```
"""
    table = extract_tabular_data(text)
    assert table is not None
    assert table.headers == ["Merchant", "Error", "Count"]
    assert len(table.rows) == 2


def test_prepare_slack_delivery_attaches_csv():
    rendered = """Summary

```
Merchant,Error,Count
thejanki.com,Shopify API Failed,18
THE GIR FARMER,invalid API key,17
```
"""
    delivery = prepare_slack_delivery(rendered, "give me a csv")
    assert len(delivery.files) == 1
    assert delivery.files[0].filename == "alfred-export.csv"
    assert b"thejanki.com" in delivery.files[0].content
    assert "*Attached:*" in delivery.text
    assert "*Preview:*" in delivery.text


def test_build_export_attachment_json():
    from backend.ingress.file_exports import TabularData

    table = TabularData(headers=["Merchant", "Count"], rows=[["a.com", "3"]])
    attachment = build_export_attachment(table, "json")
    assert attachment.filename == "alfred-export.json"
    assert b'"Merchant"' in attachment.content


def test_sanitize_fenced_backtick_pipe_table():
    raw = "\n".join(
        [
            "## 2. Impact Matrix",
            "```",
            "`File / Area | Impact Risk | Compatibility |`",
            "`---------------------------------------------`",
            "`payload-builder/utils.ts | Low | Backward-compatible |`",
            "`payload-builder/acr-checkout.ts | Low | Backward-compatible |`",
            "```",
        ]
    )
    out = format_for_slack(raw)
    assert "payload-builder/utils.ts" in out
    assert "Impact Risk" in out
    assert "`payload-builder" not in out
    assert out.count("```") == 2


def test_markdown_pr_table_converted_with_header():
    raw = "\n".join(
        [
            "| File Path | Impact Risk | Compatibility |",
            "| :--- | :--- | :--- |",
            "| payload-builder/utils.ts | Low | Backward-compatible |",
        ]
    )
    out = format_for_slack(raw)
    assert "```" in out
    assert "File Path" in out
    assert "payload-builder/utils.ts" in out

    raw = "\n".join(
        [
            "*Merchant-wise error types*",
            "`thejanki.com | Shopify API Failed | 18`",
            "`THE GIR FARMER | invalid API key | 17`",
        ]
    )
    out = format_for_slack(raw)
    assert out.count("```") == 2
    assert "thejanki.com" in out
    assert "THE GIR FARMER" in out
    assert "`thejanki.com |" not in out
