#!/usr/bin/env python3
"""Example company script package — customize locally under `.alfred/scripts/`."""

from __future__ import annotations

import json
import os
import sys

from lib.formatting import format_summary_line


def main() -> int:
    raw = (sys.argv[1] if len(sys.argv) > 1 else "") or os.environ.get("ALFRED_SCRIPT_ARGS", "{}")
    args = json.loads(raw or "{}")
    date = str(args.get("date") or "").strip()
    environment = str(args.get("environment") or "production").strip()
    if not date:
        print("error: date is required (YYYY-MM-DD)", file=sys.stderr)
        return 2

    summary = {
        "date": date,
        "environment": environment,
        "error_count": 0,
        "note": "Replace this package with your Athena/API logic.",
    }
    print(format_summary_line(date, environment, 0))
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
