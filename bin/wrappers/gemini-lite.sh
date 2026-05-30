#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export CE_TOOL_NAME="gemini-lite"
export GEMINI_MODEL="${GEMINI_MODEL:-gemini-3.1-flash-lite-preview}"
export GEMINI_THINKING_BUDGET="${GEMINI_THINKING_BUDGET:-0}"
export GEMINI_MAX_TOKENS="${GEMINI_MAX_TOKENS:-8192}"
exec "$SCRIPT_DIR/gemini.sh" "$@"
