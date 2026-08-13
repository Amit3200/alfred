"""Validate and repair self-contained HTML slide decks."""

from __future__ import annotations

import re
from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.artifacts.slide_branding import SlideBrandingContext

_SLIDE_SECTION_RE = re.compile(r'<section\s+class=["\']slide', re.I)
_SCRIPT_BLOCK_RE = re.compile(r"<script[^>]*>([\s\S]*?)</script>", re.I)
_FOOTER_TAG_RE = re.compile(r"<footer\s+class=[\"']deck-footer[\"']", re.I)
_HTML_DOCTYPE_RE = re.compile(r"<!doctype\s+html", re.I)
_REQUIRED_THEME_TOKENS = ("--bg:", "--accent:", "--text:", "ul.bullets")
_THEME_EXTRAS_CSS = """
::selection {
  background: var(--accent-soft);
  color: var(--text);
}
""".strip()

HTML_SLIDES_MAX_TOKENS = 16384


@lru_cache(maxsize=1)
def _template_tail() -> tuple[str, str]:
    from backend.paths import bundled_artifacts_static_dir

    text = (bundled_artifacts_static_dir() / "slide-template.html").read_text(encoding="utf-8")
    footer = re.search(r'<footer class="deck-footer">.*?</footer>', text, re.S | re.I)
    script = re.search(r"<script>\s*let currentSlideIndex.*?</script>", text, re.S | re.I)
    if not footer or not script:
        raise RuntimeError("slide-template.html is missing deck footer or navigation script")
    return footer.group(0), script.group(0)


def count_slides(html: str) -> int:
    return len(_SLIDE_SECTION_RE.findall(html or ""))


def has_navigation_script(html: str) -> bool:
    """True when a <script> block defines slide navigation (not just onclick attrs)."""
    for block in _SCRIPT_BLOCK_RE.findall(html or ""):
        if "updateNavUI" in block or "window.nextSlide" in block:
            return True
    return False


def deck_navigation_ready(html: str) -> bool:
    text = html or ""
    compact = re.sub(r"\s+", "", text.lower())
    return (
        has_navigation_script(text)
        and _FOOTER_TAG_RE.search(text) is not None
        and "id=\"themetoggle\"" in compact
    )


def has_required_theme_css(html: str) -> bool:
    text = html or ""
    return all(token in text for token in _REQUIRED_THEME_TOKENS)


def ensure_theme_extras(html: str) -> str:
    """Append ink/paper selection styling when the deck omits it."""
    if "::selection" in (html or ""):
        return html
    match = re.search(r"</style>", html or "", re.I)
    if not match:
        return html
    insert_at = match.start()
    return html[:insert_at] + f"\n{_THEME_EXTRAS_CSS}\n" + html[insert_at:]


def finalize_html_deck(
    html: str,
    *,
    branding: SlideBrandingContext | None = None,
) -> str:
    """Repair truncated decks, inject navigation JS, and apply company branding."""
    text = ensure_theme_extras((html or "").replace("\r\n", "\n"))
    if not text.strip() or count_slides(text) < 1:
        return apply_branding(text, branding)
    if deck_navigation_ready(text) and "</html>" in text.lower():
        return apply_branding(text, branding)

    footer, script = _template_tail()
    lower = text.lower()

    if "</html>" not in lower:
        last_section = lower.rfind("</section>")
        if last_section != -1:
            text = text[: last_section + len("</section>")]
            lower = text.lower()

    if "</main>" not in lower:
        text = text.rstrip() + "\n    </main>\n"
        lower = text.lower()

    if not _FOOTER_TAG_RE.search(text):
        text = text.rstrip() + f"\n    {footer}\n"

    if not has_navigation_script(text):
        if '<div class="deck"' in lower and text.count("<div") > text.count("</div>"):
            text = text.rstrip() + "\n  </div>\n"
        text = text.rstrip() + f"\n  {script}\n"

    if "</body>" not in text.lower():
        text = text.rstrip() + "\n</body>\n"
    if "</html>" not in text.lower():
        text = text.rstrip() + "\n</html>\n"
    return apply_branding(text, branding)


def apply_branding(html: str, branding: SlideBrandingContext | None) -> str:
    if branding is None:
        return html
    from backend.artifacts.slide_branding import apply_slide_branding

    return apply_slide_branding(html, branding)


def validate_html_deck(html: str) -> list[str]:
    """Return human-readable issues for decks that cannot be served."""
    text = finalize_html_deck(html or "")
    issues: list[str] = []
    if not _HTML_DOCTYPE_RE.search(text[:512]):
        issues.append("Missing <!DOCTYPE html>")
    if count_slides(text) < 1:
        issues.append("No slide sections found")
    if not has_required_theme_css(text):
        issues.append("Missing ink/paper theme CSS — copy tokens from html_slides skill or slide-template.html")
    if not deck_navigation_ready(text):
        issues.append("Navigation script or footer controls are missing")
    return issues
