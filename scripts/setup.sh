#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# shellcheck source=env.sh
source "$ROOT/scripts/env.sh"

PYTHON="$("$ROOT/scripts/python3.13.sh")"
echo "==> Using $("$PYTHON" --version) at $PYTHON"

if [ ! -d .venv ] || [ ".venv/pyvenv.cfg" -lt "$0" ] 2>/dev/null; then
  :
fi

if [ ! -f .venv/bin/python ] || ! .venv/bin/python -c 'import sys; exit(0 if sys.version_info[:2] == (3, 13) else 1)' 2>/dev/null; then
  echo "==> Creating .venv with Python 3.13"
  rm -rf .venv
  "$PYTHON" -m venv .venv
fi

echo "==> Installing backend (editable)"
.venv/bin/pip install --upgrade pip hatchling -q
.venv/bin/pip install -e ".[ai,dev,aws]" -q

echo "==> Installing frontend"
cd frontend
npm install
cd "$ROOT"

DATA_DIR="$ALFRED_DATA_DIR"

if [ ! -f "$DATA_DIR/config.yaml" ]; then
  echo "==> Initializing Alfred in $DATA_DIR"
  .venv/bin/alfred init --data-dir "$DATA_DIR"
fi

echo ""
echo "Setup complete."
echo "  Data dir:   $DATA_DIR"
echo "  Admin token: $(.venv/bin/alfred token --data-dir "$DATA_DIR" 2>/dev/null | tail -1)"
echo ""
echo "  Backend:  ./scripts/dev.sh"
echo "  Frontend: cd frontend && npm run dev"
