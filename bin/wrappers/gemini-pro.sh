#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export CE_TOOL_NAME="gemini-pro"
export GEMINI_MODEL="${GEMINI_MODEL:-gemini-3.1-pro-preview}"
export GEMINI_THINKING_BUDGET="${GEMINI_THINKING_BUDGET:-32768}"
exec "$SCRIPT_DIR/gemini.sh" "$@"
