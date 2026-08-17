#!/usr/bin/env python3
"""Validate Alfred tool catalog consistency (CI helper)."""

from __future__ import annotations

import sys

from backend.tools.catalog import ALL_KNOWN_TOOLS, TOOL_DOMAINS, tool_domain


def main() -> int:
    errors: list[str] = []

    if len(ALL_KNOWN_TOOLS) != len(TOOL_DOMAINS):
        missing = sorted(ALL_KNOWN_TOOLS - set(TOOL_DOMAINS))
        extra = sorted(set(TOOL_DOMAINS) - ALL_KNOWN_TOOLS)
        if missing:
            errors.append(f"TOOL_DOMAINS missing: {missing}")
        if extra:
            errors.append(f"TOOL_DOMAINS unknown keys: {extra}")

    duplicates = [name for name in TOOL_DOMAINS if tool_domain(name) == "other"]
    if duplicates:
        errors.append(f"Tools mapped to 'other' domain: {duplicates}")

    if errors:
        for err in errors:
            print(f"ERROR: {err}", file=sys.stderr)
        return 1

    print(f"OK: {len(ALL_KNOWN_TOOLS)} tools, {len(TOOL_DOMAINS)} domain mappings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
