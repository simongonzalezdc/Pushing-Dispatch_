#!/usr/bin/env bash
# codex-gpt55-high.sh - gpt-5.5 with high reasoning effort.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export CODEX_MODEL="${CODEX_MODEL:-gpt-5.5}"
export CODEX_REASONING_EFFORT="${CODEX_REASONING_EFFORT:-high}"

exec "$SCRIPT_DIR/codex.sh" "$@"
