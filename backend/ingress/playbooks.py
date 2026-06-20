"""Load domain playbooks from Markdown files in the data directory."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from backend.paths import playbooks_dir

logger = logging.getLogger(__name__)

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


@dataclass
class Playbook:
    name: str
    path: Path
    body: str
    triggers: list[str] = field(default_factory=list)
    channels: list[str] = field(default_factory=list)


class PlaybookStore:
    """Read `*.md` playbooks from `.alfred/playbooks/` and match by trigger keywords."""

    def __init__(self, data_dir: Path | None = None) -> None:
        self.directory = playbooks_dir(data_dir)
        self._playbooks: list[Playbook] | None = None

    def reload(self) -> None:
        self._playbooks = None

    def list_playbooks(self) -> list[Playbook]:
        if self._playbooks is None:
            self._playbooks = self._load_all()
        return list(self._playbooks)

    def match(self, intent: str, *, channel_id: str = "") -> list[Playbook]:
        lower = intent.lower()
        matched: list[Playbook] = []
        for playbook in self.list_playbooks():
            if playbook.channels and channel_id not in playbook.channels:
                continue
            if not playbook.triggers:
                continue
            if any(trigger.lower() in lower for trigger in playbook.triggers):
                matched.append(playbook)
        return matched

    def format_for_prompt(self, playbooks: list[Playbook]) -> str:
        if not playbooks:
            return ""
        sections = [
            "## Domain playbooks",
            "Follow these domain-specific instructions when they apply. "
            "They override generic examples above.",
            "",
        ]
        for playbook in playbooks:
            sections.append(f"### Playbook: {playbook.name}")
            sections.append(playbook.body.strip())
            sections.append("")
        return "\n".join(sections).strip()

    def _load_all(self) -> list[Playbook]:
        if not self.directory.is_dir():
            return []

        playbooks: list[Playbook] = []
        for path in sorted(self.directory.glob("*.md")):
            if path.name.lower() == "readme.md":
                continue
            try:
                playbooks.append(_parse_playbook(path))
            except Exception:
                logger.exception("Failed to load playbook %s", path)
        logger.info("Loaded %d playbook(s) from %s", len(playbooks), self.directory)
        return playbooks


def _parse_playbook(path: Path) -> Playbook:
    raw = path.read_text(encoding="utf-8")
    meta: dict = {}
    body = raw.strip()

    match = _FRONTMATTER_RE.match(raw)
    if match:
        meta = yaml.safe_load(match.group(1)) or {}
        body = raw[match.end() :].strip()

    name = str(meta.get("name") or path.stem)
    triggers = _normalize_str_list(meta.get("triggers"))
    channels = _normalize_str_list(meta.get("channels"))
    return Playbook(name=name, path=path, body=body, triggers=triggers, channels=channels)


def _normalize_str_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []
