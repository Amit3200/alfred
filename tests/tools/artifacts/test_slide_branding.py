"""Tests for HTML slide company branding."""

from __future__ import annotations

from backend.artifacts.html_deck import finalize_html_deck, has_required_theme_css
from backend.artifacts.slide_branding import (
    SlideThemeTokens,
    apply_slide_branding,
    build_slide_branding_context,
    inject_theme_tokens,
    slide_theme_from_branding,
)
from backend.models.config import AlfredConfig, BrandingConfig
from backend.paths import bundled_artifacts_static_dir

from tests.slide_fixtures import MINIMAL_SLIDE_HTML


def test_has_required_theme_css_accepts_alfred_tokens():
    assert has_required_theme_css(MINIMAL_SLIDE_HTML)


def test_slide_theme_from_branding_defaults():
    theme = slide_theme_from_branding(BrandingConfig())
    assert theme.accent == "#818cf8"
    assert theme.paper_accent == "#4f46e5"


def test_slide_theme_from_branding_custom_accent():
    theme = slide_theme_from_branding(
        BrandingConfig(slide_accent="#ff0066", slide_accent_paper="#cc0052")
    )
    assert theme.accent == "#ff0066"
    assert theme.paper_accent == "#cc0052"


def test_apply_slide_branding_updates_footer_and_tokens(tmp_path):
    config = AlfredConfig()
    config.branding.company_name = "FlexyPe"
    config.branding.setup_completed = True
    ctx = build_slide_branding_context(config, tmp_path)
    assert ctx is not None

    html = MINIMAL_SLIDE_HTML.replace(
        "Powered by Alfred",
        "Powered by <strong>Alfred</strong>",
    )
    branded = apply_slide_branding(html, ctx)
    assert "#818cf8" in branded
    assert "e07a5f" not in branded

    template = (bundled_artifacts_static_dir() / "slide-template.html").read_text(encoding="utf-8")
    branded_template = apply_slide_branding(template, ctx)
    assert "Alfred × FlexyPe" in branded_template
    assert '<span class="brand-name">FlexyPe</span>' in branded_template
    assert "nav-btn" not in branded_template


def test_strip_legacy_footer_controls():
    legacy = """
    <footer><div class="nav-controls">
    <div class="dots" id="progressDots"></div>
    <button class="nav-btn" type="button">‹</button>
    </div></footer>
    """
    cleaned = apply_slide_branding(legacy, None)
    assert "nav-btn" not in cleaned
    assert "progressDots" not in cleaned


def test_finalize_applies_branding(tmp_path):
    config = AlfredConfig()
    config.branding.company_name = "Acme Corp"
    ctx = build_slide_branding_context(config, tmp_path)
    template = (bundled_artifacts_static_dir() / "slide-template.html").read_text(encoding="utf-8")
    out = finalize_html_deck(template, branding=ctx)
    assert "Alfred × Acme Corp" in out
    assert "--accent: #818cf8" in out


def test_inject_theme_tokens_replaces_legacy_palette():
    legacy = ":root { --accent: #e07a5f; --bg: #0c0c0c; --text: #eceae4; }"
    theme = SlideThemeTokens()
    updated = inject_theme_tokens(legacy, theme)
    assert "#818cf8" in updated
    assert "#e07a5f" not in updated
