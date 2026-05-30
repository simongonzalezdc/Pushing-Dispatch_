#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export CE_TOOL_NAME="kilo-deepseek-high"
export OPENAI_COMPAT_MODEL="${OPENAI_COMPAT_MODEL:-deepseek/deepseek-v4-pro}"
export OPENAI_COMPAT_REASONING_EFFORT="${OPENAI_COMPAT_REASONING_EFFORT:-high}"
exec "$SCRIPT_DIR/kilo.sh" "$@"
