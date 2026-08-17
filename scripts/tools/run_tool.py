#!/usr/bin/env python3
"""Execute a single Alfred tool from the CLI (development / ops)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run an Alfred tool with JSON arguments.")
    parser.add_argument("--tool", required=True, help="Tool name, e.g. get_jira_issue")
    parser.add_argument("--args", default="{}", help="JSON object of tool arguments")
    parser.add_argument("--data-dir", default="", help="Alfred data dir (default: auto)")
    args = parser.parse_args()

    try:
        tool_args = json.loads(args.args)
    except json.JSONDecodeError as exc:
        print(f"Invalid --args JSON: {exc}", file=sys.stderr)
        return 2
    if not isinstance(tool_args, dict):
        print("--args must be a JSON object", file=sys.stderr)
        return 2

    from backend.config_manager import ConfigManager
    from backend.paths import get_data_dir
    from backend.tools.builder import build_git_tool_registry

    data_dir = Path(args.data_dir) if args.data_dir else get_data_dir(None)
    config, _ = ConfigManager(data_dir).load_merged()
    registry = build_git_tool_registry(config, data_dir=data_dir, allowed_tools=[args.tool])
    if args.tool not in registry._tools:
        print(f"Tool not registered: {args.tool}", file=sys.stderr)
        return 1

    result = registry.run(args.tool, tool_args, allowed=[args.tool])
    print(result.to_json())
    return 0 if result.kind != "error" else 1


if __name__ == "__main__":
    raise SystemExit(main())
