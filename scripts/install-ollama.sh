#!/usr/bin/env bash
# Install Ollama locally (macOS via Homebrew, Linux via official script).
set -euo pipefail

if command -v ollama >/dev/null 2>&1; then
  echo "Ollama is already installed: $(command -v ollama)"
  exit 0
fi

case "$(uname -s)" in
  Darwin)
    if command -v brew >/dev/null 2>&1; then
      brew install ollama
    else
      echo "Homebrew not found. Download Ollama from https://ollama.com/download"
      exit 1
    fi
    ;;
  Linux)
    curl -fsSL https://ollama.com/install.sh | sh
    ;;
  *)
    echo "Automatic install not supported on $(uname -s). See https://ollama.com/download"
    exit 1
    ;;
esac

echo ""
echo "Ollama installed. Start with: ollama serve"
echo "Or run full setup via Alfred: alfred ollama setup"
