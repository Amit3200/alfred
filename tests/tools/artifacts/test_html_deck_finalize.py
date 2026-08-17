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
    has_valid_deck_structure,
    normalize_single_html_document,
    validate_html_deck,
)
from tests.paths import REPO_ROOT


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
    path = REPO_ROOT / ".alfred" / "exports" / "presentation-1786635000.html"
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


def test_finalize_repairs_missing_top_progress_with_nav_script():
    html = """<!DOCTYPE html>
<html><head><title>Deck</title><style>
:root { --bg: #0a0a0a; --accent: #818cf8; --text: #fff; --border: #333; }
.slide { display:none; } .slide.active { display:block; }
ul.bullets { list-style: none; } ul.bullets li::before { content: "—"; }
</style></head>
<body><div class="deck"><header class="topbar">
<div class="topbar-actions">
<span id="slideCounter">1 / 2</span>
<button id="themeToggle" type="button"></button>
</div></header>
<main class="stage">
<section class="slide active"><h1>One</h1></section>
<section class="slide"><h1>Two</h1></section>
</main>
<footer class="deck-footer"><div>Powered by Alfred</div></footer>
</div>
<script>
let currentSlideIndex = 0;
const slides = document.querySelectorAll('.slide');
const topProgress = document.getElementById('topProgress');
function updateNavUI() { topProgress.style.width = '50%'; }
window.nextSlide = () => { currentSlideIndex++; updateNavUI(); };
</script>
</body></html>"""
    from backend.artifacts.html_deck import has_deck_chrome

    assert not has_deck_chrome(html)
    repaired = finalize_html_deck(html)
    assert has_deck_chrome(repaired)
    assert deck_navigation_ready(repaired)
    assert 'id="topProgress"' in repaired
    assert "if (topProgress)" in repaired
    assert not validate_html_deck(repaired)


def test_finalize_repairs_broken_shell_with_logo_in_slide():
    html = """<!DOCTYPE html>
<html><head><title>FlexyPe Daily Metrics</title><style>
:root { --bg: #0a0a0a; --accent: #818cf8; --text: #fff; --border: #333; }
.slide { display:none; } .slide.active { display:block; }
ul.bullets { list-style: none; } ul.bullets li::before { content: "—"; }
</style></head>
<body>
<section class="slide active">
<img class="brand-logo" src="data:image/png;base64,AAAA" style="height:200px" alt="FlexyPe" />
<div class="topbar-title"><span class="brand-name">FlexyPe</span><span class="deck-name">presentation</span></div>
<footer class="deck-footer"><span class="confidential">Do not distribute without permission</span></footer>
<h1>FlexyPe Daily Metrics</h1>
<div class="stat-row"><div class="stat-item"><div class="stat-value">54.9L</div></div></div>
</section>
<section class="slide"><h2>Details</h2></section>
</body></html>"""
    assert not has_valid_deck_structure(html)
    repaired = finalize_html_deck(html)
    assert has_valid_deck_structure(repaired)
    assert deck_navigation_ready(repaired)
    assert '<main class="stage">' in repaired
    assert repaired.count('class="brand-logo"') == 0 or "topbar" in repaired
    assert "touchstart" in repaired
    assert "touchend" in repaired
    assert count_slides(repaired) == 2
    assert not validate_html_deck(repaired)


def test_finalize_always_injects_touch_navigation_on_ready_deck():
    html = """<!DOCTYPE html>
<html><head><title>Deck</title><style>
:root { --bg: #0a0a0a; --accent: #818cf8; --text: #fff; --border: #333; }
.slide { display:none; } .slide.active { display:block; }
ul.bullets { list-style: none; } ul.bullets li::before { content: "—"; }
</style></head>
<body><div class="deck"><header class="topbar">
<div class="topbar-title"><span class="brand-name">Co</span></div>
<div class="topbar-actions"><span id="slideCounter">1 / 2</span>
<button id="themeToggle" type="button"></button></div></header>
<div class="progress-track"><div class="progress-fill" id="topProgress"></div></div>
<main class="stage">
<section class="slide active"><h1>One</h1></section>
<section class="slide"><h1>Two</h1></section>
</main>
<footer class="deck-footer"><div><span class="confidential">Do not distribute without permission</span></div>
<div class="powered">Powered by <strong>Alfred</strong></div></footer>
</div>
<script>
let currentSlideIndex = 0;
const slides = document.querySelectorAll('.slide');
function updateNavUI() {}
window.nextSlide = () => {};
</script>
</body></html>"""
    assert deck_navigation_ready(html)
    assert "touchstart" not in html
    repaired = finalize_html_deck(html)
    assert "touchstart" in repaired
    assert "touchend" in repaired
    assert deck_navigation_ready(repaired)


def test_finalize_collapses_duplicate_html_documents():
    from backend.paths import bundled_artifacts_static_dir

    template = (bundled_artifacts_static_dir() / "slide-template.html").read_text(encoding="utf-8")
    double = template + "\n" + template
    assert double.lower().count("<!doctype html") == 2
    repaired = finalize_html_deck(double)
    assert repaired.lower().count("<!doctype html") == 1
    assert repaired.count('class="deck"') == 1
    assert count_slides(repaired) == 4
    assert not validate_html_deck(repaired)


def test_normalize_single_html_document_prefers_richer_deck():
    from backend.paths import bundled_artifacts_static_dir

    template = (bundled_artifacts_static_dir() / "slide-template.html").read_text(encoding="utf-8")
    extra_slide = '<section class="slide"><h1>Real metrics</h1></section>'
    rich = template.replace("</main>", f"      {extra_slide}\n    </main>", 1)
    merged = template + rich
    normalized = normalize_single_html_document(merged)
    assert count_slides(normalized) == 5
    assert "Real metrics" in normalized
