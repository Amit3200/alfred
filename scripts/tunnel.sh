#!/usr/bin/env bash
set -euo pipefail

TUNNEL_NAME="${ALFRED_TUNNEL_NAME:-alfred-dev}"
CONFIG="${CLOUDFLARED_CONFIG:-$HOME/.cloudflared/config.yml}"

if ! command -v cloudflared >/dev/null 2>&1; then
  echo "cloudflared not found — install with: brew install cloudflared" >&2
  exit 1
fi

if [ ! -f "$CONFIG" ]; then
  echo "No Cloudflare tunnel config at $CONFIG — skipping public URL." >&2
  echo "Alfred still runs locally with ./scripts/up.sh (Slack, Admin UI, PR review in Slack)." >&2
  echo "To add a tunnel: cloudflared tunnel route dns alfred-dev alfred.yourdomain.dev" >&2
  exit 1
fi

exec cloudflared --config "$CONFIG" tunnel run "$TUNNEL_NAME"
