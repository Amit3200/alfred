"""Shared HTML slide fixtures for tests."""

MINIMAL_SLIDE_HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><title>Checkout Redirect</title>
<style>
:root { --bg: #0a0a0a; --accent: #818cf8; --text: #f5f5f5; --accent-soft: rgba(129, 140, 248, 0.12); --text-muted: #a3a3a3; --border: rgba(255,255,255,0.1); --bg-panel: #141414; --radius: 2px; --ease: ease; --text-dim: #737373; }
.slide{display:none}.slide.active{display:block}
ul.bullets { list-style: none; }
ul.bullets li::before { content: "→"; color: var(--accent); }
</style></head>
<body><div class="deck"><header class="topbar">
<span id="slideCounter">1 / 1</span><button id="themeToggle" type="button"></button></header>
<div class="progress-track"><div class="progress-fill" id="topProgress"></div></div>
<main class="stage"><section class="slide active"><h1>Deck</h1></section></main></div></body></html>
"""
