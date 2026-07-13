#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export CODEX_MODEL="${CODEX_MODEL:-gpt-5.6-terra}"
export CODEX_REASONING_EFFORT="${CODEX_REASONING_EFFORT:-medium}"
exec "$SCRIPT_DIR/codex.sh" "$@"
