#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export CE_TOOL_NAME="gemini-flash"
export GEMINI_MODEL="${GEMINI_MODEL:-gemini-3-flash-preview}"
export GEMINI_THINKING_BUDGET="${GEMINI_THINKING_BUDGET:-8192}"
export GEMINI_MAX_TOKENS="${GEMINI_MAX_TOKENS:-16384}"
exec "$SCRIPT_DIR/gemini.sh" "$@"
