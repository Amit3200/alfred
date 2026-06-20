#!/usr/bin/env bash
# Remove duplicate local Alfred state and optional project reset.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=env.sh
source "$ROOT/scripts/env.sh"

HOME_ALFRED="$HOME/.alfred"
PROJECT_ALFRED="$ALFRED_DATA_DIR"

echo "Project data dir: $PROJECT_ALFRED"
echo "Home data dir:    $HOME_ALFRED"

if [ -d "$HOME_ALFRED" ] && [ -d "$PROJECT_ALFRED" ]; then
  if [ "$HOME_ALFRED" != "$PROJECT_ALFRED" ]; then
    echo ""
    echo "Removing duplicate ~/.alfred (dev uses $PROJECT_ALFRED)"
    rm -rf "$HOME_ALFRED"
  fi
fi

if [ "${1:-}" = "--reset" ]; then
  echo ""
  echo "Resetting project data in $PROJECT_ALFRED"
  rm -rf "$PROJECT_ALFRED"
  mkdir -p "$PROJECT_ALFRED"
  if [ -f "$ROOT/.venv/bin/alfred" ]; then
    "$ROOT/.venv/bin/alfred" init --data-dir "$PROJECT_ALFRED"
    echo ""
    echo "New admin token:"
    "$ROOT/.venv/bin/alfred" token --data-dir "$PROJECT_ALFRED"
  else
    echo "Run ./scripts/setup.sh to re-initialize."
  fi
else
  echo ""
  echo "Done. Use --reset to wipe and re-init project .alfred"
fi
