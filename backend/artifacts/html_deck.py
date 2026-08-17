"""Validate and repair self-contained HTML slide decks."""

from __future__ import annotations

import re
from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.artifacts.slide_branding import SlideBrandingContext

_SLIDE_SECTION_RE = re.compile(r'<section\s+class=["\']slide', re.I)
_SLIDE_SECTION_FULL_RE = re.compile(
    r'<section\s+class=["\']slide[^>]*>[\s\S]*?</section>',
    re.I,
)
_SCRIPT_BLOCK_RE = re.compile(r"<script[^>]*>([\s\S]*?)</script>", re.I)
_FOOTER_TAG_RE = re.compile(r"<footer\s+class=[\"']deck-footer[\"']", re.I)
_HTML_DOCTYPE_RE = re.compile(r"<!doctype\s+html", re.I)
_ELEMENT_ID_RE = re.compile(r'\bid=(["\'])([^"\']+)\1', re.I)
_REQUIRED_NAV_IDS = ("topProgress", "slideCounter", "themeToggle")
_REQUIRED_THEME_TOKENS = ("--bg:", "--accent:", "--text:", "ul.bullets")
_THEME_EXTRAS_CSS = """
::selection {
  background: var(--accent-soft);
  color: var(--text);
}
""".strip()
_MIN_NAV_CSS = """
.progress-track { height: 1px; background: var(--border, rgba(255,255,255,0.1)); }
.progress-fill { height: 100%; width: 0%; background: var(--accent, #818cf8); transition: width 0.4s ease; }
.slide { opacity: 0; pointer-events: none; }
.slide.active { opacity: 1; pointer-events: auto; }
""".strip()
_LAYOUT_GUARD_MARKER = "Layout guards — injected by Alfred finalize"
_LAYOUT_GUARD_CSS = """
/* Layout guards — injected by Alfred finalize */
.slide img:not(.chart-img) {
  max-height: min(42vh, 320px); max-width: 100%;
  width: auto; height: auto; object-fit: contain;
}
.slide .brand-logo,
.slide .topbar-title,
.slide .deck-footer,
.slide .confidential { display: none !important; }
main.stage { touch-action: pan-y pinch-zoom; }
@media (max-width: 760px) {
  .slide { padding: 1rem 1.1rem; justify-content: flex-start; overflow-y: auto; }
  h1 { max-width: none; font-size: clamp(1.5rem, 6vw, 2rem); }
}
""".strip()

HTML_SLIDES_MAX_TOKENS = 16384


@lru_cache(maxsize=1)
def _template_shell() -> dict[str, str]:
    from backend.paths import bundled_artifacts_static_dir

    text = (bundled_artifacts_static_dir() / "slide-template.html").read_text(encoding="utf-8")
    topbar = re.search(r'<header class="topbar">.*?</header>', text, re.S | re.I)
    progress = re.search(
        r'<div class="progress-track"><div class="progress-fill" id="topProgress"></div></div>',
        text,
        re.I,
    )
    footer = re.search(r'<footer class="deck-footer">.*?</footer>', text, re.S | re.I)
    script = re.search(r"<script>\s*let currentSlideIndex.*?</script>", text, re.S | re.I)
    if not topbar or not progress or not footer or not script:
        raise RuntimeError("slide-template.html is missing deck shell or navigation script")
    return {
        "topbar": topbar.group(0),
        "progress": progress.group(0),
        "footer": footer.group(0),
        "script": script.group(0),
    }


def count_slides(html: str) -> int:
    return len(_SLIDE_SECTION_RE.findall(html or ""))


def _has_element_id(html: str, element_id: str) -> bool:
    needle = element_id.lower()
    for match in _ELEMENT_ID_RE.finditer(html or ""):
        if match.group(2).lower() == needle:
            return True
    return False


def has_deck_chrome(html: str) -> bool:
    """True when all navigation DOM hooks exist."""
    text = html or ""
    return all(_has_element_id(text, element_id) for element_id in _REQUIRED_NAV_IDS)


def has_navigation_script(html: str) -> bool:
    """True when a <script> block defines slide navigation (not just onclick attrs)."""
    for block in _SCRIPT_BLOCK_RE.findall(html or ""):
        if "updateNavUI" in block or "window.nextSlide" in block:
            return True
    return False


def deck_navigation_ready(html: str) -> bool:
    text = html or ""
    return (
        has_navigation_script(text)
        and _FOOTER_TAG_RE.search(text) is not None
        and has_deck_chrome(text)
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


def ensure_min_nav_css(html: str) -> str:
    """Ensure slide/progress CSS exists so repaired decks still animate."""
    text = html or ""
    if ".progress-track" in text and ".slide.active" in text:
        return text
    match = re.search(r"</style>", text, re.I)
    if not match:
        return text
    insert_at = match.start()
    return text[:insert_at] + f"\n{_MIN_NAV_CSS}\n" + text[insert_at:]


def ensure_layout_guard_css(html: str) -> str:
    """Inject CSS that prevents broken slide layouts (oversized logos, chrome in body)."""
    text = html or ""
    if ".slide .brand-logo" in text and "display: none !important" in text:
        return text
    match = re.search(r"</style>", text, re.I)
    if not match:
        return text
    insert_at = match.start()
    return text[:insert_at] + f"\n{_LAYOUT_GUARD_CSS}\n" + text[insert_at:]


def _extract_slide_sections(html: str) -> list[str]:
    return _SLIDE_SECTION_FULL_RE.findall(html or "")


def _sanitize_slide_body(slide_html: str) -> str:
    """Remove misplaced chrome (logos, topbar, footer) from slide content."""
    text = slide_html or ""
    text = re.sub(
        r'<img[^>]*class=["\'][^"\']*brand-logo[^"\']*["\'][^>]*/?>',
        "",
        text,
        flags=re.I,
    )
    text = re.sub(
        r'<header\s+class=["\']topbar["\'][^>]*>[\s\S]*?</header>',
        "",
        text,
        flags=re.I,
    )
    text = re.sub(
        r'<footer\s+class=["\']deck-footer["\'][^>]*>[\s\S]*?</footer>',
        "",
        text,
        flags=re.I,
    )
    text = re.sub(
        r'<div\s+class=["\']topbar-title["\'][^>]*>[\s\S]*?</div>',
        "",
        text,
        flags=re.I,
    )
    text = re.sub(
        r'<div\s+class=["\']progress-track["\'][^>]*>[\s\S]*?</div>',
        "",
        text,
        flags=re.I,
    )
    return text


def _sanitize_slides_in_place(html: str) -> str:
    """Sanitize each slide section without rebuilding the full shell."""
    text = html or ""

    def _replace(match: re.Match[str]) -> str:
        return _sanitize_slide_body(match.group(0))

    return _SLIDE_SECTION_FULL_RE.sub(_replace, text)


def _slides_inside_stage(html: str) -> bool:
    stage_match = re.search(
        r'<main\s+class=["\']stage["\'][^>]*>([\s\S]*?)</main>',
        html or "",
        re.I,
    )
    if not stage_match:
        return False
    all_slides = _extract_slide_sections(html)
    stage_slides = _extract_slide_sections(stage_match.group(1))
    return len(all_slides) > 0 and len(all_slides) == len(stage_slides)


def has_valid_deck_structure(html: str) -> bool:
    """True when deck shell matches slide-template.html anatomy."""
    text = html or ""
    if not re.search(r'<div\s+class=["\']deck["\']', text, re.I):
        return False
    if not re.search(r'<header\s+class=["\']topbar["\']', text, re.I):
        return False
    if not re.search(r'<main\s+class=["\']stage["\']', text, re.I):
        return False
    if not _FOOTER_TAG_RE.search(text):
        return False
    if not _slides_inside_stage(text):
        return False

    topbar_pos = re.search(r'<header\s+class=["\']topbar["\']', text, re.I)
    main_pos = re.search(r'<main\s+class=["\']stage["\']', text, re.I)
    footer_pos = _FOOTER_TAG_RE.search(text)
    if not (topbar_pos and main_pos and footer_pos):
        return False
    if topbar_pos.start() > main_pos.start():
        return False
    if main_pos.start() > footer_pos.start():
        return False

    for slide in _extract_slide_sections(text):
        if re.search(r'<header\s+class=["\']topbar["\']', slide, re.I):
            return False
        if re.search(r'<footer\s+class=["\']deck-footer["\']', slide, re.I):
            return False
        if re.search(r'class=["\'][^"\']*brand-logo[^"\']*["\']', slide, re.I):
            return False
        if re.search(r'class=["\']confidential["\']', slide, re.I):
            return False
    return True


def _ensure_first_slide_active(slides: list[str]) -> list[str]:
    if not slides:
        return slides
    first = slides[0]
    if re.search(r'class=["\']slide\s+active["\']', first, re.I):
        return slides
    updated = re.sub(
        r'class=(["\'])slide(\1)',
        r'class="slide active"',
        first,
        count=1,
        flags=re.I,
    )
    return [updated, *slides[1:]]


def _rebuild_deck_shell(html: str) -> str:
    """Extract slide sections and wrap them in the canonical deck shell."""
    slides = [_sanitize_slide_body(s) for s in _extract_slide_sections(html)]
    if not slides:
        return html
    slides = _ensure_first_slide_active(slides)
    shell = _template_shell()
    slides_block = "\n      ".join(slides)
    grid_bg = '<div class="grid-bg" aria-hidden="true"></div>'
    body_content = f"""
  {grid_bg}

  <div class="deck">
    {shell["topbar"]}
    {shell["progress"]}

    <main class="stage">
      {slides_block}
    </main>

    {shell["footer"]}
  </div>
"""
    body_open = re.search(r"<body[^>]*>", html, re.I)
    body_close = re.search(r"</body>", html, re.I)
    if body_open and body_close:
        return html[: body_open.end()] + body_content + "\n" + html[body_close.start() :]
    return html.rstrip() + body_content


def ensure_deck_structure(html: str) -> str:
    """Rebuild or sanitize deck shell so slides render inside main.stage only."""
    text = html or ""
    if not _extract_slide_sections(text):
        return text
    if has_valid_deck_structure(text):
        return _sanitize_slides_in_place(text)
    return _rebuild_deck_shell(text)


def _insert_before_main_or_slides(text: str, block: str) -> str:
    main_match = re.search(r"<main\s+class=[\"']stage[\"']", text, re.I)
    if main_match:
        return text[: main_match.start()] + block + "\n    " + text[main_match.start() :]
    slide_match = re.search(r"<section\s+class=[\"']slide", text, re.I)
    if slide_match:
        return text[: slide_match.start()] + block + "\n      " + text[slide_match.start() :]
    return text


def ensure_deck_chrome(html: str) -> str:
    """Inject missing topbar/progress controls required by the nav script."""
    text = html or ""
    shell = _template_shell()

    if not _has_element_id(text, "topProgress"):
        progress_track = re.search(r'<div\s+class=["\']progress-track["\']', text, re.I)
        if progress_track:
            text, count = re.subn(
                r'(<div\s+class=["\']progress-track["\'][^>]*>\s*<div)([^>]*)(>)',
                lambda match: (
                    f'{match.group(1)} class="progress-fill" id="topProgress"{match.group(3)}'
                    if "id=" not in match.group(2).lower()
                    else match.group(0)
                ),
                text,
                count=1,
                flags=re.I,
            )
            if count and _has_element_id(text, "topProgress"):
                pass
            elif progress_track:
                text = re.sub(
                    r'(<div\s+class=["\']progress-track["\'][^>]*>)',
                    r'\1<div class="progress-fill" id="topProgress"></div>',
                    text,
                    count=1,
                    flags=re.I,
                )
        else:
            text = _insert_before_main_or_slides(text, shell["progress"])

    if not _has_element_id(text, "slideCounter") or not _has_element_id(text, "themeToggle"):
        topbar_actions = re.search(r'<div\s+class=["\']topbar-actions["\']', text, re.I)
        if topbar_actions:
            if not _has_element_id(text, "slideCounter"):
                text = re.sub(
                    r'(<div\s+class=["\']topbar-actions["\'][^>]*>)',
                    r'\1\n        <span class="slide-counter" id="slideCounter">1 / 1</span>',
                    text,
                    count=1,
                    flags=re.I,
                )
            if not _has_element_id(text, "themeToggle"):
                text = re.sub(
                    r'(<div\s+class=["\']topbar-actions["\'][^>]*>)',
                    r'\1\n        <button class="theme-btn" id="themeToggle" type="button">ink / paper</button>',
                    text,
                    count=1,
                    flags=re.I,
                )
        elif re.search(r"<header[^>]*class=[\"'][^\"']*topbar", text, re.I):
            text = re.sub(
                r"(</header>)",
                "      <div class=\"topbar-actions\">\n"
                "        <span class=\"slide-counter\" id=\"slideCounter\">1 / 1</span>\n"
                "        <button class=\"theme-btn\" id=\"themeToggle\" type=\"button\">ink / paper</button>\n"
                "      </div>\n    \\1",
                text,
                count=1,
                flags=re.I,
            )
        else:
            insert = shell["topbar"] + "\n    "
            if not _has_element_id(text, "topProgress"):
                insert += shell["progress"] + "\n    "
            text = _insert_before_main_or_slides(text, insert)

    return text


def strip_navigation_scripts(html: str) -> str:
    """Remove broken or duplicate slide navigation scripts."""

    def _replace(match: re.Match[str]) -> str:
        body = match.group(1)
        if (
            "updateNavUI" in body
            or "window.nextSlide" in body
            or "currentSlideIndex" in body
        ):
            return ""
        return match.group(0)

    return _SCRIPT_BLOCK_RE.sub(_replace, html or "")


def has_canonical_navigation_script(html: str) -> bool:
    """True when the bundled nav script is present (keyboard + touch + null-safe hooks)."""
    for block in _SCRIPT_BLOCK_RE.findall(html or ""):
        if (
            "updateNavUI" in block
            and "window.nextSlide" in block
            and "touchstart" in block
            and "SWIPE_MIN" in block
            and "if (topProgress)" in block
        ):
            return True
    return False


def ensure_canonical_navigation_script(html: str) -> str:
    """Always use the bundled navigation script so DOM hooks stay in sync."""
    text = html or ""
    if has_canonical_navigation_script(text):
        return text
    text = strip_navigation_scripts(text)
    shell = _template_shell()
    script = shell["script"]
    body_close = re.search(r"</body>", text, re.I)
    if body_close:
        insert_at = body_close.start()
        return text[:insert_at] + f"\n  {script}\n" + text[insert_at:]
    return text.rstrip() + f"\n  {script}\n"


def _ensure_deck_wrapper(html: str) -> str:
    text = html or ""
    lower = text.lower()
    if '<div class="deck"' in lower or "<div class='deck'" in lower:
        return text
    body_open = re.search(r"<body[^>]*>", text, re.I)
    body_close = re.search(r"</body>", text, re.I)
    if not body_open or not body_close:
        return text
    inner = text[body_open.end() : body_close.start()].strip()
    wrapped = (
        text[: body_open.end()]
        + '\n  <div class="deck">\n    '
        + inner
        + "\n  </div>\n"
        + text[body_close.start() :]
    )
    return wrapped


def _ensure_main_stage(html: str) -> str:
    text = html or ""
    if re.search(r"<main\s+class=[\"']stage[\"']", text, re.I):
        return text
    slides = list(_SLIDE_SECTION_RE.finditer(text))
    if not slides:
        return text
    first = slides[0].start()
    last = slides[-1].end()
    block = text[first:last]
    return text[:first] + '<main class="stage">\n      ' + block + "\n    </main>" + text[last:]


def _ensure_footer(html: str) -> str:
    text = html or ""
    if _FOOTER_TAG_RE.search(text):
        return text
    shell = _template_shell()
    lower = text.lower()
    if "</main>" in lower:
        return re.sub(r"</main>", f"</main>\n\n    {shell['footer']}", text, count=1, flags=re.I)
    return text.rstrip() + f"\n    {shell['footer']}\n"


def _ensure_document_closure(html: str) -> str:
    text = (html or "").rstrip()
    lower = text.lower()
    if "</body>" not in lower:
        text += "\n</body>\n"
    if "</html>" not in lower:
        text += "</html>\n"
    return text


def finalize_html_deck(
    html: str,
    *,
    branding: SlideBrandingContext | None = None,
) -> str:
    """Repair truncated decks, inject navigation JS, and apply company branding."""
    text = ensure_theme_extras((html or "").replace("\r\n", "\n"))
    if not text.strip() or count_slides(text) < 1:
        return apply_branding(text, branding)

    lower = text.lower()
    if "</html>" not in lower:
        last_section = lower.rfind("</section>")
        if last_section != -1:
            text = text[: last_section + len("</section>")]
            lower = text.lower()

    text = ensure_deck_structure(text)
    text = _ensure_deck_wrapper(text)
    text = _ensure_main_stage(text)
    text = ensure_min_nav_css(text)
    text = ensure_layout_guard_css(text)
    text = ensure_deck_chrome(text)
    text = _ensure_footer(text)
    text = ensure_canonical_navigation_script(text)
    text = _ensure_document_closure(text)
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
    if not has_deck_chrome(text):
        issues.append("Navigation chrome is missing (#topProgress, #slideCounter, or #themeToggle)")
    if not has_navigation_script(text):
        issues.append("Navigation script is missing")
    if not _FOOTER_TAG_RE.search(text):
        issues.append("Footer is missing")
    if not has_valid_deck_structure(text):
        issues.append("Deck shell is invalid — slides must live inside main.stage with topbar/footer outside")
    return issues
