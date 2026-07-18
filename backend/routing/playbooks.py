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
    triggers: list[str] = field(default_factory=list)
    channels: list[str] = field(default_factory=list)
    repos: list[str] = field(default_factory=list)
    description: str = ""
    mode: SkillMode = "conversational"
    allowed_tools: list[str] = field(default_factory=list)
    requires_thread_context: bool = False
    bundled: bool = False
    fetch_urls: list[str] = field(default_factory=list)
    fetch_ttl_minutes: int = 60
    _body: str | None = field(default=None, repr=False, compare=False)

    @property
    def body(self) -> str:
        if self._body is None:
            object.__setattr__(self, "_body", _read_body(self.path))
        return self._body

    @property
    def body_loaded(self) -> bool:
        return self._body is not None


class PlaybookStore:
    """Read playbooks from `.alfred/playbooks/` and bundled `skills/`.

    Routing tiers load **metadata only** (frontmatter). Full markdown bodies are
    read on demand when formatting the active playbook for the agent prompt.
    """

    def __init__(
        self,
        data_dir: Path | None = None,
        *,
        disabled_skills: list[str] | None = None,
    ) -> None:
        self.data_dir = data_dir
        self.directory = playbooks_dir(data_dir)
        self.disabled_skills = {name.strip().lower() for name in (disabled_skills or [])}
        self._playbooks: list[Playbook] | None = None
        self._cache_mtime: float = 0.0

    def set_disabled_skills(self, names: list[str]) -> None:
        new_set = {name.strip().lower() for name in names}
        if new_set != self.disabled_skills:
            self.disabled_skills = new_set
            self.reload()

    def reload(self) -> None:
        self._playbooks = None
        self._cache_mtime = 0.0

    def list_playbooks(self) -> list[Playbook]:
        mtime = self._sources_mtime()
        if self._playbooks is None or mtime > self._cache_mtime:
            self._playbooks = self._load_index()
            self._cache_mtime = mtime
        return list(self._playbooks)

    def _sources_mtime(self) -> float:
        latest = _tree_mtime(self.directory)
        latest = max(latest, _tree_mtime(bundled_skills_dir()))
        return latest

    def match(
        self,
        intent: str,
        *,
        channel_id: str = "",
        repo: str = "",
    ) -> list[Playbook]:
        """Return all playbooks whose triggers appear in *intent* (debug / legacy API)."""
        lower = intent.lower()
        repo_lower = repo.strip().lower()
        matched: list[Playbook] = []
        for playbook in self.list_playbooks():
            if not self._passes_routing_filters(playbook, lower, channel_id, repo_lower):
                continue
            if _best_trigger_len(playbook, lower) > 0:
                matched.append(playbook)
        return matched

    def pick_conversational(
        self,
        intent: str,
        *,
        channel_id: str = "",
        repo: str = "",
    ) -> Playbook | None:
        """Return the single best conversational playbook (longest trigger wins)."""
        return self._pick_best(
            intent,
            channel_id=channel_id,
            repo=repo,
            modes=("conversational",),
        )

    def pick_investigation(
        self,
        intent: str,
        *,
        channel_id: str = "",
        repo: str = "",
    ) -> Playbook | None:
        """Return the best-matching investigation skill (longest trigger wins)."""
        return self._pick_best(
            intent,
            channel_id=channel_id,
            repo=repo,
            modes=("investigation", "workflow"),
            require_tools=False,
        )

    def _pick_best(
        self,
        intent: str,
        *,
        channel_id: str = "",
        repo: str = "",
        modes: tuple[str, ...],
        require_tools: bool = False,
    ) -> Playbook | None:
        lower = intent.lower()
        repo_lower = repo.strip().lower()
        best: Playbook | None = None
        best_len = 0
        for playbook in self.list_playbooks():
            if playbook.mode not in modes:
                continue
            if require_tools and not playbook.allowed_tools:
                continue
            if not self._passes_routing_filters(playbook, lower, channel_id, repo_lower):
                continue
            trigger_len = _best_trigger_len(playbook, lower)
            if trigger_len > best_len:
                best = playbook
                best_len = trigger_len
        return best

    def _passes_routing_filters(
        self,
        playbook: Playbook,
        intent_lower: str,
        channel_id: str,
        repo_lower: str,
    ) -> bool:
        if playbook.channels and channel_id not in playbook.channels:
            return False
        if playbook.repos and repo_lower and not _repo_matches(
            playbook.repos, intent_lower, repo_lower
        ):
            return False
        if not playbook.triggers:
            return False
        return True

    def get_by_name(self, name: str) -> Playbook | None:
        """Return a playbook/skill by name (metadata only until ``body`` is accessed)."""
        target = name.strip().lower()
        for playbook in self.list_playbooks():
            if playbook.name.lower() == target:
                return playbook
        return None

    def format_catalog_for_prompt(
        self,
        *,
        channel_id: str = "",
        repo: str = "",
        max_triggers: int = 4,
    ) -> str:
        """Compact index of available playbooks/skills — metadata only, no bodies."""
        repo_lower = repo.strip().lower()
        visible = [
            playbook
            for playbook in self.list_playbooks()
            if self._passes_catalog_filters(playbook, channel_id, repo_lower)
        ]
        if not visible:
            return ""

        skills = sorted(
            (p for p in visible if p.mode in ("investigation", "workflow")),
            key=lambda p: p.name.lower(),
        )
        playbooks = sorted(
            (p for p in visible if p.mode == "conversational"),
            key=lambda p: p.name.lower(),
        )

        sections = [
            "## Available playbooks & skills",
            "You have the entries below registered locally. "
            "Only the **Active playbook** section (when present) contains full instructions "
            "for the current request — do not invent or assume playbook content from this index.",
            "",
        ]
        if skills:
            sections.append("### Skills")
            for playbook in skills:
                sections.append(_format_catalog_entry(playbook, max_triggers=max_triggers))
            sections.append("")
        if playbooks:
            sections.append("### Domain playbooks")
            for playbook in playbooks:
                sections.append(_format_catalog_entry(playbook, max_triggers=max_triggers))
        return "\n".join(sections).strip()

    def format_routed_prompt(
        self,
        active: Playbook | None,
        *,
        channel_id: str = "",
        repo: str = "",
        data_dir: Path | None = None,
    ) -> str:
        """Catalog index plus the active playbook body when matched; otherwise catalog only."""
        catalog = self.format_catalog_for_prompt(channel_id=channel_id, repo=repo)
        if active is None:
            return catalog
        active_section = self.format_for_prompt([active], data_dir=data_dir)
        if catalog and active_section:
            return f"{catalog}\n\n{active_section}"
        return active_section or catalog

    def _passes_catalog_filters(
        self,
        playbook: Playbook,
        channel_id: str,
        repo_lower: str,
    ) -> bool:
        if playbook.channels and channel_id not in playbook.channels:
            return False
        if playbook.repos and repo_lower:
            for repo in playbook.repos:
                needle = repo.strip().lower()
                if repo_lower == needle or repo_lower.endswith("/" + needle.split("/")[-1]):
                    return True
            return False
        return True

    def format_for_prompt(self, playbooks: list[Playbook], *, data_dir: Path | None = None) -> str:
        if not playbooks:
            return ""
        sections = [
            "## Active playbook (loaded for this request)",
            "Follow these instructions for this turn. They override generic examples above.",
            "",
        ]
        for playbook in playbooks:
            label = "Skill" if playbook.mode in ("investigation", "workflow") else "Playbook"
            sections.append(f"### {label}: {playbook.name}")
            sections.append(playbook.body.strip())
            sections.append("")

        from backend.routing.playbook_fetch import format_playbook_dynamic_context

        dynamic = format_playbook_dynamic_context(playbooks, data_dir=data_dir)
        if dynamic:
            sections.extend(["", dynamic, ""])
        return "\n".join(sections).strip()

    def _load_index(self) -> list[Playbook]:
        playbooks: list[Playbook] = []
        seen_names: set[str] = set()

        for path in sorted(self.directory.rglob("*.md")) if self.directory.is_dir() else []:
            if path.name.lower() == "readme.md":
                continue
            try:
                playbook = _parse_playbook_index(path, bundled=False)
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
                    playbook = _parse_playbook_index(path, bundled=True)
                    if playbook.name.lower() in self.disabled_skills:
                        continue
                    if playbook.name.lower() in seen_names:
                        continue
                    playbooks.append(playbook)
                except Exception:
                    logger.exception("Failed to load skill %s", path)

        logger.info("Indexed %d playbook/skill file(s) (metadata only)", len(playbooks))
        return playbooks


def _tree_mtime(directory: Path) -> float:
    if not directory.is_dir():
        return 0.0
    latest = 0.0
    for path in directory.rglob("*.md"):
        try:
            latest = max(latest, path.stat().st_mtime)
        except OSError:
            continue
    return latest


def _read_body(path: Path) -> str:
    raw = path.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(raw)
    if match:
        return raw[match.end() :].strip()
    return raw.strip()


def _parse_playbook_index(path: Path, *, bundled: bool) -> Playbook:
    raw = path.read_text(encoding="utf-8")
    meta: dict = {}

    match = _FRONTMATTER_RE.match(raw)
    if match:
        meta = yaml.safe_load(match.group(1)) or {}

    name = str(meta.get("name") or path.stem)
    description = str(meta.get("description") or "").strip()
    triggers = _normalize_str_list(meta.get("triggers") or meta.get("trigger_keywords"))
    channels = _normalize_channels(meta.get("channels") or meta.get("allowed_channels"))
    repos = _normalize_str_list(meta.get("repos"))
    mode = str(meta.get("mode") or "conversational")
    if mode not in ("conversational", "investigation", "workflow"):
        mode = "conversational"
    allowed_tools = _normalize_str_list(meta.get("allowed_tools"))
    requires_thread_context = bool(meta.get("requires_thread_context", False))
    fetch_urls = _normalize_str_list(meta.get("fetch_urls"))
    fetch_ttl_minutes = int(meta.get("fetch_ttl_minutes") or 60)

    if channels == ["*"]:
        channels = []

    return Playbook(
        name=name,
        path=path,
        triggers=triggers,
        channels=channels,
        repos=repos,
        description=description,
        mode=mode,  # type: ignore[arg-type]
        allowed_tools=allowed_tools,
        requires_thread_context=requires_thread_context,
        bundled=bundled,
        fetch_urls=fetch_urls,
        fetch_ttl_minutes=max(1, fetch_ttl_minutes),
    )


def _parse_playbook(path: Path, *, bundled: bool) -> Playbook:
    """Parse metadata and eagerly load body — admin API / tests."""
    playbook = _parse_playbook_index(path, bundled=bundled)
    object.__setattr__(playbook, "_body", _read_body(path))
    return playbook


def _normalize_str_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


_SLACK_CHANNEL_ID_RE = re.compile(r"^C[A-Z0-9]{8,}$", re.IGNORECASE)


def _normalize_channels(value: object) -> list[str]:
    channels = _normalize_str_list(value)
    if not channels or channels == ["*"]:
        return []
    slack_ids = [ch for ch in channels if _SLACK_CHANNEL_ID_RE.match(ch)]
    return slack_ids


def _best_trigger_len(playbook: Playbook, intent_lower: str) -> int:
    best = 0
    for trigger in playbook.triggers:
        token = trigger.lower()
        if token not in intent_lower:
            continue

        idx = intent_lower.find(token)
        while idx != -1:
            left_ok = True
            if idx > 0:
                char_left = intent_lower[idx - 1]
                if char_left.isalnum() or char_left == "_":
                    left_ok = False

            right_ok = True
            end_idx = idx + len(token)
            if end_idx < len(intent_lower):
                char_right = intent_lower[end_idx]
                if char_right.isalnum() or char_right == "_":
                    right_ok = False

            if left_ok and right_ok:
                if len(token) > best:
                    best = len(token)
                break

            idx = intent_lower.find(token, idx + 1)
    return best


def _format_catalog_entry(playbook: Playbook, *, max_triggers: int) -> str:
    label = playbook.description or playbook.name.replace("_", " ").replace("-", " ")
    shown = playbook.triggers[:max_triggers]
    trigger_bits = ", ".join(f"`{token}`" for token in shown)
    if len(playbook.triggers) > max_triggers:
        trigger_bits += f", +{len(playbook.triggers) - max_triggers} more"
    repo_note = f" [{', '.join(playbook.repos)}]" if playbook.repos else ""
    kind = "skill" if playbook.mode in ("investigation", "workflow") else "playbook"
    return f"- **{playbook.name}** ({kind}{repo_note}) — {label}. Triggers: {trigger_bits}"


def _repo_matches(repos: list[str], intent_lower: str, repo_lower: str) -> bool:
    """Match repo-scoped playbooks when task repo or intent mentions the repo."""
    if repo_lower:
        for repo in repos:
            needle = repo.strip().lower()
            if not needle:
                continue
            if repo_lower == needle or repo_lower.endswith("/" + needle.split("/")[-1]):
                return True
    for repo in repos:
        needle = repo.strip().lower()
        if not needle:
            continue
        if needle in intent_lower:
            return True
        short = needle.split("/")[-1]
        if short and short in intent_lower:
            return True
    return False
