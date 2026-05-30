#!/usr/bin/env bash
# codex-spark.sh - Manifest OpenAI gpt-5.3-codex-spark lane via Codex CLI.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export CODEX_MODEL="${CODEX_MODEL:-gpt-5.3-codex-spark}"
export CODEX_REASONING_EFFORT="${CODEX_REASONING_EFFORT:-medium}"

exec "$SCRIPT_DIR/codex.sh" "$@"
