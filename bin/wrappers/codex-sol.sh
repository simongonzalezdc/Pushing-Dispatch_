#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export CODEX_MODEL="${CODEX_MODEL:-gpt-5.6-sol}"
export CODEX_REASONING_EFFORT="${CODEX_REASONING_EFFORT:-low}"
case "$CODEX_REASONING_EFFORT" in
    low|medium|high) ;;
    *)
        echo "Error: GPT-5.6 Sol reasoning is capped at high; use low, medium, or high, then stop and reassess." >&2
        exit 1
        ;;
esac
exec "$SCRIPT_DIR/codex.sh" "$@"
