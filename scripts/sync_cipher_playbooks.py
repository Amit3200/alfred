#!/usr/bin/env python3
"""Sync FlexyPe Cipher skill runbooks into `.alfred/playbooks/cipher/`."""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

import yaml

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

DEFAULT_SOURCE = Path(
    "/Users/amit3200/workspace/flexype/cipher/Skill Generation Matrix"
)
CIPHER_REPO = "FlexyPe/cipher"


def _alfred_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _transform_frontmatter(meta: dict) -> dict:
    """Adapt Cipher agent skills for Alfred playbook loading."""
    out = dict(meta)

    # Alfred uses Slack channel IDs (C…); Cipher skills use #channel names.
    out.pop("allowed_channels", None)
    out["channels"] = []

    # Scope to Cipher repo when Alfred adds repo-aware matching.
    repos = out.get("repos")
    if not repos:
        out["repos"] = [CIPHER_REPO]

    triggers = out.get("triggers") or out.get("trigger_keywords") or []
    if isinstance(triggers, str):
        triggers = [triggers]
    out["triggers"] = list(triggers)
    out.pop("trigger_keywords", None)

    # Shell-style tool strings are for the Cipher DevOps agent, not Alfred tools.
    out.pop("allowed_tools", None)

    return out


def _transform_file(content: str) -> str:
    match = _FRONTMATTER_RE.match(content)
    if not match:
        return content
    meta = yaml.safe_load(match.group(1)) or {}
    body = content[match.end() :]
    new_meta = _transform_frontmatter(meta)
    header = yaml.safe_dump(new_meta, sort_keys=False, allow_unicode=True).strip()
    return f"---\n{header}\n---\n{body}"


def sync(source: Path, dest_root: Path, *, dry_run: bool = False) -> int:
    if not source.is_dir():
        print(f"Source not found: {source}", file=sys.stderr)
        return 1

    skill_files = sorted(
        p for p in source.rglob("*.md") if p.name.lower() != "readme.md"
    )
    if not skill_files:
        print(f"No skill files under {source}", file=sys.stderr)
        return 1

    if dry_run:
        for path in skill_files:
            rel = path.relative_to(source)
            print(f"would copy: {rel} -> cipher/{rel}")
        print(f"total: {len(skill_files)} files")
        return 0

    if dest_root.exists():
        shutil.rmtree(dest_root)
    dest_root.mkdir(parents=True)

    for path in skill_files:
        rel = path.relative_to(source)
        dest = dest_root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(_transform_file(path.read_text(encoding="utf-8")), encoding="utf-8")

    readme = source / "README.md"
    if readme.is_file():
        index_meta = {
            "name": "cipher-skill-index",
            "repos": [CIPHER_REPO],
            "channels": [],
            "triggers": [
                "cipher skill",
                "cipher runbook",
                "cipher devops",
                "skill generation matrix",
                "FlexyPe/cipher",
            ],
        }
        header = yaml.safe_dump(index_meta, sort_keys=False, allow_unicode=True).strip()
        body = readme.read_text(encoding="utf-8")
        if _FRONTMATTER_RE.match(body):
            body = _FRONTMATTER_RE.sub("", body, count=1).lstrip()
        index = dest_root / "cipher-skill-index.md"
        index.write_text(f"---\n{header}\n---\n\n{body}", encoding="utf-8")

    print(f"Synced {len(skill_files)} cipher skill(s) to {dest_root}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE,
        help=f"Skill Generation Matrix directory (default: {DEFAULT_SOURCE})",
    )
    parser.add_argument(
        "--dest",
        type=Path,
        default=_alfred_root() / ".alfred" / "playbooks" / "cipher",
        help="Destination under .alfred/playbooks/",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    return sync(args.source, args.dest, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
