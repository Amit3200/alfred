"""Tests for playbook URL fetching."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from backend.ingress.playbook_fetch import (
    fetch_url_text,
    format_playbook_dynamic_context,
    html_to_text,
    validate_fetch_url,
)
from backend.ingress.playbooks import Playbook, PlaybookStore


def test_validate_fetch_url_https_only() -> None:
    assert validate_fetch_url("https://example.com") == "https://example.com"
    with pytest.raises(ValueError):
        validate_fetch_url("http://example.com")
    with pytest.raises(ValueError):
        validate_fetch_url("https://127.0.0.1")


def test_html_to_text_strips_scripts() -> None:
    html = "<html><head><script>ignore()</script></head><body><h1>Example Corp</h1><p>Checkout suite</p></body></html>"
    text = html_to_text(html)
    assert "Example Corp" in text
    assert "Checkout suite" in text
    assert "ignore" not in text


def test_fetch_url_text_uses_cache(tmp_path) -> None:
    html = "<html><body><p>Live marketing copy</p></body></html>"

    class FakeResponse:
        content = html.encode("utf-8")
        encoding = "utf-8"
        headers = {"content-type": "text/html"}

        @staticmethod
        def raise_for_status() -> None:
            return None

    with patch("backend.ingress.playbook_fetch.requests.get", return_value=FakeResponse()) as get:
        text1, note1 = fetch_url_text("https://example.com", data_dir=tmp_path, ttl_minutes=60)
        text2, note2 = fetch_url_text("https://example.com", data_dir=tmp_path, ttl_minutes=60)

    assert "Live marketing copy" in (text1 or "")
    assert "live snapshot" in (note1 or "")
    assert "cached snapshot" in (note2 or "")
    get.assert_called_once()


def test_format_for_prompt_includes_dynamic_sources(tmp_path) -> None:
    playbooks_dir = tmp_path / "playbooks"
    playbooks_dir.mkdir()
    (playbooks_dir / "company.md").write_text(
        """---
name: company
triggers:
  - example corp
fetch_urls:
  - https://example.com
---

Static body.
""",
        encoding="utf-8",
    )
    store = PlaybookStore(tmp_path)
    matched = store.match("what is example corp?")
    html = "<html><body><p>Website headline about checkout</p></body></html>"

    class FakeResponse:
        content = html.encode("utf-8")
        encoding = "utf-8"
        headers = {"content-type": "text/html"}

        @staticmethod
        def raise_for_status() -> None:
            return None

    with patch("backend.ingress.playbook_fetch.requests.get", return_value=FakeResponse()):
        prompt = store.format_for_prompt(matched, data_dir=tmp_path)

    assert "Static body" in prompt
    assert "Live web sources" in prompt
    assert "Website headline about checkout" in prompt


def test_format_playbook_dynamic_context_empty_without_urls(tmp_path) -> None:
    playbook = Playbook(name="x", path=tmp_path / "x.md", body="body")
    assert format_playbook_dynamic_context([playbook], data_dir=tmp_path) == ""
