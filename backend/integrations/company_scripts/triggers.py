"""Match company script packages by manifest trigger phrases."""

from __future__ import annotations

import re
from pathlib import Path

from backend.integrations.company_scripts.catalog import CompanyScriptStore
from backend.models.config import AlfredConfig

_TRIGGER_RE_CACHE: dict[str, re.Pattern[str]] = {}


def _trigger_pattern(phrase: str) -> re.Pattern[str]:
    key = phrase.lower()
    if key not in _TRIGGER_RE_CACHE:
        escaped = re.escape(key)
        _TRIGGER_RE_CACHE[key] = re.compile(rf"\b{escaped}\b", re.I)
    return _TRIGGER_RE_CACHE[key]


def match_script_by_trigger(
    text: str,
    *,
    data_dir: Path | None,
    config: AlfredConfig,
) -> str | None:
    """Return script package name when user text matches a manifest trigger."""
    store = CompanyScriptStore(data_dir, config=config)
    haystack = (text or "").strip()
    if not haystack:
        return None

    best: tuple[float, str] | None = None
    for script in store.list_scripts():
        for phrase in script.triggers:
            if _trigger_pattern(phrase).search(haystack):
                score = len(phrase) / max(len(haystack), 1)
                if best is None or score > best[0]:
                    best = (score, script.name)
    return best[1] if best else None
