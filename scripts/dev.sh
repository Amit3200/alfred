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

echo "Alfred API → http://${ALFRED_HOST}:${ALFRED_PORT}  (data: $ALFRED_DATA_DIR)"
exec .venv/bin/alfred serve \
  --host "$ALFRED_HOST" \
  --port "$ALFRED_PORT" \
  --data-dir "$ALFRED_DATA_DIR" \
  --reload
