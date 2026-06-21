#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# shellcheck source=env.sh
source "$ROOT/scripts/env.sh"

if [ ! -f .venv/bin/alfred ]; then
  echo "Run ./scripts/setup.sh first" >&2
  exit 1
fi

exec .venv/bin/alfred up \
  --data-dir "$ALFRED_DATA_DIR" \
  --host "$ALFRED_HOST" \
  --port "$ALFRED_PORT" \
  --frontend-port "$ALFRED_FRONTEND_PORT" \
  --with-frontend \
  "$@"
