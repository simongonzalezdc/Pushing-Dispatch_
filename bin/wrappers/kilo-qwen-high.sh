#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export CE_TOOL_NAME="kilo-qwen-high"
export OPENAI_COMPAT_MODEL="${OPENAI_COMPAT_MODEL:-qwen/qwen3.7-max}"
export OPENAI_COMPAT_REASONING_EFFORT="${OPENAI_COMPAT_REASONING_EFFORT:-high}"
exec "$SCRIPT_DIR/kilo.sh" "$@"
