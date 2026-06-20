#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "==> Building admin UI"
cd frontend
npm install
npm run build
cd "$ROOT"

mkdir -p backend/static/admin
rm -rf backend/static/admin/*
cp -R frontend/dist/* backend/static/admin/

echo "==> Building Python package"
pip install build
python -m build

echo "==> Done. Artifacts in dist/"
