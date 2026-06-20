#!/usr/bin/env bash
# Shared Alfred dev environment — source from other scripts.
ALFRED_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export ALFRED_DATA_DIR="${ALFRED_DATA_DIR:-$ALFRED_ROOT/.alfred}"
export ALFRED_HOST="${ALFRED_HOST:-127.0.0.1}"
export ALFRED_PORT="${ALFRED_PORT:-8080}"
