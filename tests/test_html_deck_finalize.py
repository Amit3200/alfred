"""Tests for HTML deck finalize/repair."""

from __future__ import annotations

from pathlib import Path

from backend.artifacts.html_deck import (
    count_slides,
    deck_navigation_ready,
    ensure_theme_extras,
    finalize_html_deck,
    has_navigation_script,
    has_required_theme_css,
    validate_html_deck,
)


def test_has_required_theme_css():
    from backend.paths import bundled_artifacts_static_dir

    html = (bundled_artifacts_static_dir() / "slide-template.html").read_text(encoding="utf-8")
    assert has_required_theme_css(html)


def test_ensure_theme_extras_adds_selection_styling():
    html = "<!DOCTYPE html><html><head><style>:root{--accent-soft:#000;--text:#fff}</style></head><body></body></html>"
    out = ensure_theme_extras(html)
    assert "::selection" in out


def test_finalize_footer_without_script_still_injects_navigation():
    html = """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><title>Deck</title>
<style>.slide{display:none}.slide.active{display:block}</style></head>
<body><div class="deck"><header class="topbar">
<span id="slideCounter">1 / 2</span><button id="themeToggle" type="button"></button></header>
<div class="progress-track"><div id="topProgress"></div></div><main class="stage">
<section class="slide active"><h1>One</h1></section>
<section class="slide"><h1>Two</h1></section>
</main>
<footer class="deck-footer">
  <button type="button" onclick="nextSlide()">Next</button>
</footer>
</div></body></html>"""
    assert not has_navigation_script(html)
    repaired = finalize_html_deck(html)
    assert has_navigation_script(repaired)
    assert deck_navigation_ready(repaired)


def test_finalize_truncated_export_adds_navigation():
    path = Path(__file__).resolve().parents[1] / ".alfred" / "exports" / "presentation-1786635000.html"
    if not path.is_file():
        html = """<!DOCTYPE html>
<html><head><title>Test</title><style>.slide{display:none}.slide.active{display:flex}</style></head>
<body><div class="deck"><main class="stage">
<section class="slide active"><h1>One</h1></section>
<section class="slide"><h1>Two</h1></section>
<section class="slide"><h1>Three incomplete"""
    else:
        html = path.read_text(encoding="utf-8")

    assert not deck_navigation_ready(html)
    repaired = finalize_html_deck(html)
    assert deck_navigation_ready(repaired)
    assert "nextSlide" in repaired
    assert "</html>" in repaired.lower()
    assert count_slides(repaired) >= 1
    assert not validate_html_deck(repaired)


def test_finalize_idempotent_for_complete_template():
    from backend.paths import bundled_artifacts_static_dir

    html = (bundled_artifacts_static_dir() / "slide-template.html").read_text(encoding="utf-8")
    assert deck_navigation_ready(html)
    once = finalize_html_deck(html)
    twice = finalize_html_deck(once)
    assert once == twice
    assert not validate_html_deck(twice)
