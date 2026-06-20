#!/usr/bin/env bash
# Resolve Python 3.13 for local dev (Homebrew on Apple Silicon, pyenv, or PATH).
set -euo pipefail

if command -v python3.13 >/dev/null 2>&1; then
  echo "$(command -v python3.13)"
elif [ -x /opt/homebrew/bin/python3.13 ]; then
  echo /opt/homebrew/bin/python3.13
elif [ -x /usr/local/bin/python3.13 ]; then
  echo /usr/local/bin/python3.13
else
  echo "Python 3.13 not found. Install with: brew install python@3.13" >&2
  exit 1
fi
