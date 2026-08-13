---
name: html_slides
description: Create polished self-contained HTML slide decks from data, stats, conversations, charts, and images.
mode: investigation
trigger_keywords:
  - slide deck
  - html slides
  - presentation
  - create slides
  - deck
allowed_channels:
  - "*"
requires_thread_context: false
allowed_tools:
  - save_html_deck
  - publish_html_artifact
---

# HTML Slides

Build a **single self-contained HTML file** when the user provides data, metrics, conversation summaries, charts, or **screenshots/images attached in the prompt**.

**Do not fetch external sites at generation time.** Use the bundled **terminal deck** aesthetic: deep ink background (`#0a0a0a`), sharp 1px borders, **2px max radius**, Inter/Geist headlines, JetBrains Mono labels, `table.data-table`, `.stat-row` KPI strips (not rounded cards), and numbered `.feature-row` sections. Copy the full CSS and structure from `backend/static/artifacts/slide-template.html`.

**Company branding:** Alfred injects configured company name (**exact casing**, e.g. `FlexyPe`), logo, and accent colors from admin **Company profile** / `branding.slide_accent` at save/publish time. Company accent **overrides** default palette when set.

## When to use

- User asks for slides, a deck, or an HTML presentation
- Stats, incident reviews, roadmaps, meeting summaries, charts, or **attached screenshots** need a presentation
- User may later ask to **publish** — that is optional (see Delivery)

## Images & screenshots (required for self-contained HTML)

All images must live **inside the HTML file** so it works offline and when shared as one file.

| Source | How to embed |
|--------|----------------|
| Image attached in chat prompt | Read the image bytes → base64 → `data:image/png;base64,...` or `data:image/jpeg;base64,...` |
| Chart generated in-session | Inline SVG, `<canvas>` + small script, or PNG as data URI |
| Slack thread screenshot (if visible to you) | Same data URI — never rely on Slack private URLs in final HTML |
| User-supplied logo | Data URI or user-provided stable HTTPS URL only if they insist |

**Slide patterns for images:**

```html
<section class="slide">
  <div class="slide-label">screenshot</div>
  <h2>Checkout error state</h2>
  <div class="panel">
    <img src="data:image/png;base64,AAAA..." alt="Screenshot description" />
  </div>
</section>
```

- One screenshot per slide when detail matters; use `.two-col` for image + bullet commentary
- Always set meaningful `alt` text
- Keep total file under ~10 MB (artifact limit); compress or split slides if many large images

## Delivery (default vs publish)

**Default — user did NOT ask to publish/host/share a URL:**

1. Build complete HTML with embedded images
2. Call **`save_html_deck`** (writes to `.alfred/exports/`, returns download path)
3. Reply with a short summary + note that the `.html` file is attached or saved
4. Do **not** call `publish_html_artifact` or `POST /api/artifacts`

On Slack, Alfred auto-attaches HTML when the reply contains a full deck. Admin chat: use `save_html_deck` → user downloads from exports.

**Only when user explicitly asks** to publish, host, upload, or get a share link:

1. Confirm or ask for a **slug** (e.g. `redirection-2025`)
2. Call **`publish_html_artifact`** with `html`, `slug`, and optional `title`.
   - **Slack:** omit `uploaded_by` / `owner_key` — Alfred auto-assigns from the requester (`slack:{user_id}`) and tracks `source=slack`.
   - **Admin:** omit actor fields when possible; admin login identity is used.
3. Return public URL: `/artifacts/s/{slug}`

Trigger words for publish: *publish, host, upload, share link, put on artifacts, give me a URL*

## Design snapshot (ink / paper)

Sharp terminal layout — flat borders, data-forward tables, no glow orbs or pill KPI cards.

### Tokens — dark (`:root`, default **ink**)

| Token | Default | Use |
|-------|---------|-----|
| `--bg` | `#0a0a0a` | Page background |
| `--bg-panel` | `#141414` | Terminal panels |
| `--border` | `rgba(255,255,255,0.1)` | Hairline borders |
| `--text` | `#f5f5f5` | Primary text |
| `--text-muted` | `#a3a3a3` | Body secondary |
| `--text-dim` | `#737373` | Footer hints, feature index |
| `--accent` | `#818cf8` (or `branding.slide_accent`) | Progress, labels, hero `<em>` |
| `--font-sans` | `Inter, Geist, system-ui…` | Headlines, brand name |
| `--font-mono` | `JetBrains Mono, SF Mono…` | Labels, tables, deck subtitle |
| `--radius` | `2px` | Buttons, panels — **never** large radii |

### Tokens — light (`body.paper-mode`, **paper**)

| Token | Default |
|-------|---------|
| `--bg` | `#fafafa` |
| `--accent` | `#4f46e5` (or `branding.slide_accent_paper`) |
| `--text` | `#171717` |

### Slide layout patterns

| Pattern | Classes | When to use |
|---------|---------|-------------|
| Hero headline | `h1` + `<em>keyword</em>` | Title slide — accent one keyword |
| Stat strip | `.stat-row` > `.stat-item` | 3–4 headline metrics — **grid with borders**, not cards |
| Data table | `table.data-table` | Daily metrics — mono headers, tabular nums |
| Numbered insight | `.feature-row` + `.feature-index` | “01 / 02 / 03” sections with flat top border |
| Terminal block | `.terminal-panel` | Query output, monospace data |
| Bullets | `ul.bullets` | Findings — `—` prefix in accent |

**Avoid:** `.card-grid`, rounded pill metrics, glow orbs, footer prev/next buttons.

### Layout anatomy

```
┌ topbar: brand-name · deck-name (mono) · counter · ink/paper toggle ─┐
├ progress track (1px, --accent fill) ────────────────────────────────┤
│  .stage (full viewport)                                              │
│    section.slide × N (absolute stack, .active = visible)             │
├ footer: confidential · kbd hint · Powered by Alfred ─────────────────┤
└ subtle grid-bg (fixed) ──────────────────────────────────────────────┘
```

### Interaction (required)

| Input | Action |
|-------|--------|
| `→` `↓` `Space` `PageDown` | Next slide |
| `←` `↑` `Backspace` `PageUp` | Previous slide |
| `Home` / `End` | First / last slide |
| `#themeToggle` click | Toggle `body.paper-mode` |

**No footer nav buttons or dot pagination** — keyboard + top progress bar only.

Slide transition: `opacity 0→1` + `translateY(10px→0)`, ~400ms, `--ease`. No autoplay.

### Slide patterns

- **Title**: `.slide-label` + `h1` with `<em>` accent word + `.rule` + `.lead` + optional `.stat-row`
- **Tables**: `table.data-table` with `thead` / `tbody` — `.metric-cell`, `.accent-cell` for emphasis
- **Numbered sections**: `.feature-row` with `.feature-index` (01…) + `.feature-body`
- **Split content**: `.two-col` — narrative left, `.terminal-panel` right
- **Bullets**: `ul.bullets` — `—` prefix in accent color

### Mandatory chrome

1. `<!DOCTYPE html>` — **all CSS and JS inline** (no build step, no external stylesheets)
2. Footer left: **`Do not distribute without permission`** (exact wording)
3. Footer right: **`Powered by Alfred`** or **`Powered by Alfred × {company}`** when branding is configured
4. Topbar: `<span class="brand-name">` for company (exact casing from config) + `<span class="deck-name">` for deck title
5. Top progress bar + slide counter — **no** dot nav or chevron buttons
6. Default theme: **ink** (dark)

## Reference skeleton

Start from **`backend/static/artifacts/slide-template.html`** — copy the entire `<style>` block, HTML shell, and navigation `<script>` verbatim. Duplicate `<section class="slide">` blocks inside `<main class="stage">`.

Admin preview: `GET /api/artifacts/template/slides`

## Full inline CSS

**Copy the `<style>` block from `backend/static/artifacts/slide-template.html` verbatim.** Do not invent alternate palettes, radii, or card layouts. Key rules:

- `--radius: 2px` max
- `.brand-name` — sans, bold, **no** `text-transform: lowercase`
- `.stat-row` — bordered grid, not `.card-grid`
- `table.data-table` — mono headers, 1px row borders
- No `.glow`, `.nav-btn`, `.dots`, or `.card-grid`

## Content rules

- 3–12 slides typical; **one idea per slide**
- Title slide + metrics + analysis + next steps is a good default arc
- Conversation data → decisions, actions, open questions on separate slides
- Use the deck title in `<title>` and `<span class="deck-name">` — company name goes in `<span class="brand-name">` (Alfred injects exact casing at save time)

## Workflow

1. Parse user data (stats, thread, charts, **attached images**)
2. Outline slides; dedicate slide(s) to screenshots where relevant
3. Clone template CSS/JS; embed all images as **data URIs**
4. **Default:** `save_html_deck` → deliver raw `.html` file
5. **If asked to publish:** `publish_html_artifact` → return `/artifacts/s/{slug}`

## Do not

- Fetch external URLs for styling — use this embedded snapshot only
- Call `publish_html_artifact` unless the user explicitly asked to publish/host/share
- Use external image URLs for screenshots (they break offline / expire)
- Use legacy coral palette (`#e07a5f`) or rounded `.card-grid` KPI boxes
- Add footer prev/next buttons, dot pagination, or glow orbs
- Lowercase the company name in the topbar
- Remove confidential footer or Alfred × company attribution
- Ship multi-file decks (breaks single-file delivery)
- Autoplay slides
