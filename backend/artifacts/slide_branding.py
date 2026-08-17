"""Company branding and terminal-deck theme tokens for HTML slide decks."""

from __future__ import annotations

import base64
import html
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.branding.display import branding_display_title, branding_tagline
from backend.branding.store import LogoStore
from backend.models.config import AlfredConfig, BrandingConfig

_ROOT_BLOCK_RE = re.compile(r":root\s*\{[^}]*\}", re.S | re.I)
_PAPER_MODE_BLOCK_RE = re.compile(r"body\.paper-mode\s*\{[^}]*\}", re.S | re.I)
_POWERED_RE = re.compile(r"Powered by\s*<strong>Alfred</strong>", re.I)
_TOPBAR_TITLE_RE = re.compile(
    r'(<div class="topbar-title">)(.*?)(</div>)',
    re.S | re.I,
)
_NAV_BTN_RE = re.compile(
    r'<button[^>]*class="[^"]*nav-btn[^"]*"[^>]*>.*?</button>',
    re.S | re.I,
)
_NAV_CONTROLS_RE = re.compile(
    r'<div class="nav-controls">.*?</div>',
    re.S | re.I,
)
_DOTS_CONTAINER_RE = re.compile(r'<div class="dots"[^>]*id="progressDots"[^>]*></div>', re.I)

_FONT_SANS = '"Inter", "Geist", ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif'
_FONT_MONO = '"JetBrains Mono", "SF Mono", ui-monospace, Menlo, monospace'

# Neutral Alfred defaults — overridden by branding.slide_accent when configured.
_DEFAULT_INK_ACCENT = "#818cf8"
_DEFAULT_PAPER_ACCENT = "#4f46e5"
_DEFAULT_ACCENT_SECONDARY = "#a5b4fc"


@dataclass(frozen=True)
class SlideThemeTokens:
    """Ink/paper CSS variables — sharp terminal-deck layout."""

    bg: str = "#0a0a0a"
    bg_elevated: str = "#111111"
    bg_panel: str = "#141414"
    border: str = "rgba(255, 255, 255, 0.1)"
    border_strong: str = "rgba(255, 255, 255, 0.16)"
    text: str = "#f5f5f5"
    text_muted: str = "#a3a3a3"
    text_dim: str = "#737373"
    accent: str = _DEFAULT_INK_ACCENT
    accent_soft: str = "rgba(129, 140, 248, 0.12)"
    accent_secondary: str = _DEFAULT_ACCENT_SECONDARY
    glow: str = "rgba(129, 140, 248, 0.08)"
    paper_bg: str = "#fafafa"
    paper_bg_elevated: str = "#ffffff"
    paper_bg_panel: str = "#ffffff"
    paper_border: str = "rgba(0, 0, 0, 0.1)"
    paper_border_strong: str = "rgba(0, 0, 0, 0.16)"
    paper_text: str = "#171717"
    paper_text_muted: str = "#525252"
    paper_text_dim: str = "#737373"
    paper_accent_soft: str = "rgba(79, 70, 229, 0.08)"
    paper_glow: str = "rgba(79, 70, 229, 0.05)"
    paper_accent: str = _DEFAULT_PAPER_ACCENT
    radius: str = "2px"

    def css_root_block(self) -> str:
        return f""":root {{
      --bg: {self.bg};
      --bg-elevated: {self.bg_elevated};
      --bg-panel: {self.bg_panel};
      --border: {self.border};
      --border-strong: {self.border_strong};
      --text: {self.text};
      --text-muted: {self.text_muted};
      --text-dim: {self.text_dim};
      --accent: {self.accent};
      --accent-soft: {self.accent_soft};
      --accent-secondary: {self.accent_secondary};
      --glow: {self.glow};
      --font-sans: {_FONT_SANS};
      --font-mono: {_FONT_MONO};
      --ease: cubic-bezier(0.22, 1, 0.36, 1);
      --radius: {self.radius};
    }}"""

    def css_paper_mode_block(self) -> str:
        return f"""body.paper-mode {{
      --bg: {self.paper_bg};
      --bg-elevated: {self.paper_bg_elevated};
      --bg-panel: {self.paper_bg_panel};
      --border: {self.paper_border};
      --border-strong: {self.paper_border_strong};
      --text: {self.paper_text};
      --text-muted: {self.paper_text_muted};
      --text-dim: {self.paper_text_dim};
      --accent: {self.paper_accent};
      --accent-soft: {self.paper_accent_soft};
      --glow: {self.paper_glow};
    }}"""


@dataclass(frozen=True)
class SlideBrandingContext:
    company_name: str
    tagline: str
    display_title: str
    theme: SlideThemeTokens
    logo_data_uri: str = ""

    @property
    def has_company(self) -> bool:
        return bool(self.company_name)


def _hex_to_rgb_triplet(value: str) -> tuple[int, int, int] | None:
    raw = (value or "").strip().lstrip("#")
    if len(raw) == 3:
        raw = "".join(ch * 2 for ch in raw)
    if len(raw) != 6 or not re.fullmatch(r"[0-9a-fA-F]{6}", raw):
        return None
    return int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)


def _rgba(accent_hex: str, alpha: float, *, fallback: str = "129, 140, 248") -> str:
    rgb = _hex_to_rgb_triplet(accent_hex)
    if rgb is None:
        return f"rgba({fallback}, {alpha})"
    r, g, b = rgb
    return f"rgba({r}, {g}, {b}, {alpha})"


def slide_theme_from_branding(branding: BrandingConfig) -> SlideThemeTokens:
    """Company branding colors take precedence when set in config."""
    accent = (branding.slide_accent or "").strip() or _DEFAULT_INK_ACCENT
    paper_accent = (branding.slide_accent_paper or "").strip() or _DEFAULT_PAPER_ACCENT
    secondary = (branding.slide_accent_secondary or "").strip() or _DEFAULT_ACCENT_SECONDARY
    rgb_fallback = ",".join(str(v) for v in (_hex_to_rgb_triplet(accent) or (129, 140, 248)))
    return SlideThemeTokens(
        accent=accent,
        accent_soft=_rgba(accent, 0.12, fallback=rgb_fallback),
        accent_secondary=secondary,
        glow=_rgba(accent, 0.08, fallback=rgb_fallback),
        paper_accent=paper_accent,
        paper_accent_soft=_rgba(paper_accent, 0.08, fallback=rgb_fallback),
        paper_glow=_rgba(paper_accent, 0.05, fallback=rgb_fallback),
    )


def load_logo_data_uri(data_dir: Path | None) -> str:
    if data_dir is None:
        return ""
    existing = LogoStore(data_dir).existing()
    if existing is None:
        return ""
    path, _ext = existing
    try:
        raw = path.read_bytes()
    except OSError:
        return ""
    ext = path.suffix.lstrip(".").lower()
    mime = LogoStore.media_type_for_extension(ext)
    encoded = base64.b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def build_slide_branding_context(
    config: AlfredConfig | None,
    data_dir: Path | None = None,
) -> SlideBrandingContext | None:
    if config is None:
        return None
    branding = config.branding
    company = branding.company_name or ""
    theme = slide_theme_from_branding(branding)
    return SlideBrandingContext(
        company_name=company,
        tagline=branding_tagline(branding),
        display_title=branding_display_title(branding),
        theme=theme,
        logo_data_uri=load_logo_data_uri(data_dir),
    )


def html_slides_branding_prompt(ctx: SlideBrandingContext) -> str:
    accent_note = (
        f"Configured company accent: ink `{ctx.theme.accent}`, paper `{ctx.theme.paper_accent}`."
        if ctx.theme.accent != _DEFAULT_INK_ACCENT
        else f"Default accent (set `branding.slide_accent` to override): `{ctx.theme.accent}`."
    )
    lines = [
        "\n\n## Slide design system (terminal deck + company branding)",
        accent_note,
        "- **Layout first** — sharp 1px borders, 2px radius max, no rounded KPI cards or pill boxes.",
        "- **Fonts** — Inter/Geist sans for headlines; JetBrains Mono for labels, tables, counters.",
        "- **Data** — `table.data-table` for tabular metrics; `.stat-row` for headline KPIs (grid with borders, not cards).",
        "- **Insights** — `.feature-row` with small mono index (01, 02) + flat body copy.",
        "- **Navigation** — keyboard (← → space), swipe left/right on mobile, tap stage edges; no footer prev/next buttons.",
        "- **Shell (mandatory)** — copy `slide-template.html` body structure verbatim:",
        "  - `<div class=\"grid-bg\">` + `<div class=\"deck\">` wrapper",
        "  - `<header class=\"topbar\">` once, **outside** slides — logo only here as `<img class=\"brand-logo\">` (~1rem tall)",
        "  - `<main class=\"stage\">` contains **only** `<section class=\"slide\">` blocks",
        "  - `<footer class=\"deck-footer\">` once, **outside** slides — never duplicate confidential/powered-by text inside slides",
        "- **Never** put company logo, topbar, footer, or \"Do not distribute\" inside a `<section class=\"slide\">`.",
        "- Copy CSS/structure from `backend/static/artifacts/slide-template.html` verbatim.",
    ]
    if ctx.has_company:
        lines.append(
            f"- Topbar company name **exact casing**: `{ctx.company_name}` in `<span class=\"brand-name\">` — never lowercase."
        )
        lines.append(f'- Footer: `Powered by Alfred × {ctx.company_name}`')
    else:
        lines.append("- Footer: `Powered by Alfred`")
    if ctx.logo_data_uri:
        lines.append(
            '- Logo **only in topbar** before brand name: `<img class="brand-logo" … />` — never full-size inside slides'
        )
    return "\n".join(lines) + "\n"


def _brand_logo_markup(ctx: SlideBrandingContext) -> str:
    if ctx.logo_data_uri:
        alt = html.escape(ctx.company_name or "Company logo")
        return f'<img class="brand-logo" src="{ctx.logo_data_uri}" alt="{alt}" />'
    return ""


def _extract_deck_name(topbar_inner: str) -> str:
    if "deck-name" in topbar_inner:
        match = re.search(r'<span class="deck-name">(.*?)</span>', topbar_inner, re.S | re.I)
        if match:
            return match.group(1).strip()
    if "·" in topbar_inner:
        return topbar_inner.split("·", 1)[-1].strip()
    if "<strong>deck</strong>" in topbar_inner.lower():
        return topbar_inner.split("</strong>", 1)[-1].lstrip(" ·").strip()
    return "presentation"


def _build_topbar_title(ctx: SlideBrandingContext, deck_name: str) -> str:
    logo = _brand_logo_markup(ctx)
    logo_block = f"{logo} " if logo else ""
    company = html.escape(ctx.company_name)
    deck = html.escape(deck_name or "presentation")
    return (
        f'{logo_block}<span class="brand-name">{company}</span>'
        f'<span class="topbar-sep">·</span>'
        f'<span class="deck-name">{deck}</span>'
    )


def inject_company_chrome(text: str, ctx: SlideBrandingContext) -> str:
    updated = text
    if ctx.has_company:
        powered = f"Powered by <strong>Alfred × {html.escape(ctx.company_name)}</strong>"
        updated = _POWERED_RE.sub(powered, updated, count=1)

        def _topbar_replace(match: re.Match[str]) -> str:
            deck_name = _extract_deck_name(match.group(2))
            title = _build_topbar_title(ctx, deck_name)
            return f"{match.group(1)}{title}{match.group(3)}"

        updated = _TOPBAR_TITLE_RE.sub(_topbar_replace, updated, count=1)
    return updated


def strip_legacy_footer_controls(text: str) -> str:
    """Remove old prev/next buttons and dot nav from repaired decks."""
    updated = _NAV_BTN_RE.sub("", text)
    updated = _NAV_CONTROLS_RE.sub("", updated)
    updated = _DOTS_CONTAINER_RE.sub("", updated)
    updated = re.sub(
        r"const dotsContainer = document\.getElementById\('progressDots'\);[\s\S]*?const dots = document\.querySelectorAll\('\.dot'\);\n",
        "",
        updated,
    )
    updated = re.sub(
        r"\s*dots\.forEach\(\(d, i\) => d\.classList\.toggle\('active', i === currentSlideIndex\)\);\n",
        "",
        updated,
    )
    return updated


def inject_theme_tokens(text: str, theme: SlideThemeTokens) -> str:
    updated = text
    root = theme.css_root_block()
    if _ROOT_BLOCK_RE.search(updated):
        updated = _ROOT_BLOCK_RE.sub(root, updated, count=1)
    else:
        style_open = re.search(r"<style[^>]*>", updated, re.I)
        if style_open:
            insert_at = style_open.end()
            updated = updated[:insert_at] + f"\n    {root}\n" + updated[insert_at:]

    paper = theme.css_paper_mode_block()
    if _PAPER_MODE_BLOCK_RE.search(updated):
        updated = _PAPER_MODE_BLOCK_RE.sub(paper, updated, count=1)
    elif ":root" in updated:
        updated = updated.replace(root, f"{root}\n\n    {paper}", 1)

    if ".brand-name" not in updated:
        style_close = re.search(r"</style>", updated, re.I)
        if style_close:
            chrome_css = """
    .brand-name {
      font-family: var(--font-sans); font-weight: 650; letter-spacing: -0.02em;
      color: var(--text); text-transform: none;
    }
    .brand-logo { height: 0.95rem; width: auto; vertical-align: middle; margin-right: 0.35rem; }
    .topbar-sep { color: var(--text-dim); font-family: var(--font-mono); }
    .deck-name {
      font-family: var(--font-mono); font-size: 0.74rem; letter-spacing: 0.03em;
      color: var(--text-muted);
    }
"""
            updated = updated[: style_close.start()] + chrome_css + updated[style_close.start() :]

    return updated


def apply_slide_branding(text: str, ctx: SlideBrandingContext | None) -> str:
    if not (text or "").strip():
        return text
    updated = strip_legacy_footer_controls(text)
    if ctx is None:
        return updated
    updated = inject_theme_tokens(updated, ctx.theme)
    updated = inject_company_chrome(updated, ctx)
    return updated


def branding_context_from_registry(registry: Any) -> SlideBrandingContext | None:
    config = getattr(registry, "alfred_config", None)
    data_dir = getattr(registry, "data_dir", None)
    return build_slide_branding_context(config, data_dir)
