#!/bin/sh
set -e

DATA_DIR="${ALFRED_DATA_DIR:-/data/.alfred}"
export ALFRED_DATA_DIR="$DATA_DIR"

if [ ! -f "$DATA_DIR/config.yaml" ]; then
  echo "First run — initializing Alfred in $DATA_DIR"
  alfred init --data-dir "$DATA_DIR"
fi

exec alfred "$@" --data-dir "$DATA_DIR"
