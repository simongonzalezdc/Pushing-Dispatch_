#!/usr/bin/env bash
# codex-gpt55.sh - Manifest OpenAI gpt-5.5 lane via native Codex CLI.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export CODEX_MODEL="${CODEX_MODEL:-gpt-5.5}"
export CODEX_REASONING_EFFORT="${CODEX_REASONING_EFFORT:-xhigh}"

exec "$SCRIPT_DIR/codex.sh" "$@"
