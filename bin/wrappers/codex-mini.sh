#!/usr/bin/env bash
# codex-mini.sh - Manifest OpenAI gpt-5.4-mini lane via native Codex CLI.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export CODEX_MODEL="${CODEX_MODEL:-gpt-5.4-mini}"
export CODEX_REASONING_EFFORT="${CODEX_REASONING_EFFORT:-low}"

exec "$SCRIPT_DIR/codex.sh" "$@"
