#!/usr/bin/env bash
# codex-oss.sh - Dispatch a local Codex worker through Ollama or another OSS provider.
#
# Raspberry Pi / local model default:
#   CODEX_LOCAL_PROVIDER=ollama
#   CODEX_MODEL=<an installed Ollama model>

set -euo pipefail

export CODEX_OSS=1
export CODEX_LOCAL_PROVIDER="${CODEX_LOCAL_PROVIDER:-ollama}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/codex.sh" "$@"
