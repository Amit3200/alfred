"""Load domain playbooks and bundled skills from Markdown files."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml

from backend.paths import bundled_skills_dir, playbooks_dir

logger = logging.getLogger(__name__)

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

SkillMode = Literal["conversational", "investigation", "workflow"]


@dataclass
class Playbook:
    name: str
    path: Path
    body: str
    triggers: list[str] = field(default_factory=list)
    channels: list[str] = field(default_factory=list)
    mode: SkillMode = "conversational"
    allowed_tools: list[str] = field(default_factory=list)
    requires_thread_context: bool = False
    bundled: bool = False


class PlaybookStore:
    """Read playbooks from `.alfred/playbooks/` and bundled `skills/`."""

    def __init__(
        self,
        data_dir: Path | None = None,
        *,
        disabled_skills: list[str] | None = None,
    ) -> None:
        self.directory = playbooks_dir(data_dir)
        self.disabled_skills = {name.strip().lower() for name in (disabled_skills or [])}
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

    def pick_investigation(self, intent: str, *, channel_id: str = "") -> Playbook | None:
        """Return the best-matching investigation skill (longest trigger wins)."""
        lower = intent.lower()
        best: Playbook | None = None
        best_len = 0
        for playbook in self.match(intent, channel_id=channel_id):
            if playbook.mode != "investigation" or not playbook.allowed_tools:
                continue
            for trigger in playbook.triggers:
                token = trigger.lower()
                if token in lower and len(token) > best_len:
                    best = playbook
                    best_len = len(token)
        return best

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
            label = "Skill" if playbook.mode == "investigation" else "Playbook"
            sections.append(f"### {label}: {playbook.name}")
            sections.append(playbook.body.strip())
            sections.append("")
        return "\n".join(sections).strip()

    def _load_all(self) -> list[Playbook]:
        playbooks: list[Playbook] = []
        seen_names: set[str] = set()

        for path in sorted(self.directory.glob("*.md")) if self.directory.is_dir() else []:
            if path.name.lower() == "readme.md":
                continue
            try:
                playbook = _parse_playbook(path, bundled=False)
                playbooks.append(playbook)
                seen_names.add(playbook.name.lower())
            except Exception:
                logger.exception("Failed to load playbook %s", path)

        skills_root = bundled_skills_dir()
        if skills_root.is_dir():
            for path in sorted(skills_root.glob("*.md")):
                if path.name.lower() == "readme.md":
                    continue
                try:
                    playbook = _parse_playbook(path, bundled=True)
                    if playbook.name.lower() in self.disabled_skills:
                        continue
                    if playbook.name.lower() in seen_names:
                        continue
                    playbooks.append(playbook)
                except Exception:
                    logger.exception("Failed to load skill %s", path)

        logger.info("Loaded %d playbook/skill file(s)", len(playbooks))
        return playbooks


def _parse_playbook(path: Path, *, bundled: bool) -> Playbook:
    raw = path.read_text(encoding="utf-8")
    meta: dict = {}
    body = raw.strip()

    match = _FRONTMATTER_RE.match(raw)
    if match:
        meta = yaml.safe_load(match.group(1)) or {}
        body = raw[match.end() :].strip()

    name = str(meta.get("name") or path.stem)
    triggers = _normalize_str_list(meta.get("triggers") or meta.get("trigger_keywords"))
    channels = _normalize_str_list(meta.get("channels") or meta.get("allowed_channels"))
    mode = str(meta.get("mode") or "conversational")
    if mode not in ("conversational", "investigation", "workflow"):
        mode = "conversational"
    allowed_tools = _normalize_str_list(meta.get("allowed_tools"))
    requires_thread_context = bool(meta.get("requires_thread_context", False))

    if channels == ["*"]:
        channels = []

    return Playbook(
        name=name,
        path=path,
        body=body,
        triggers=triggers,
        channels=channels,
        mode=mode,  # type: ignore[arg-type]
        allowed_tools=allowed_tools,
        requires_thread_context=requires_thread_context,
        bundled=bundled,
    )


def _normalize_str_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []
