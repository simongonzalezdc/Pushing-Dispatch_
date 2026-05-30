#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export CE_TOOL_NAME="kilo-free"
export OPENAI_COMPAT_MODEL="${OPENAI_COMPAT_MODEL:-x-ai/grok-code-fast-1:optimized:free}"
export OPENAI_COMPAT_MAX_TOKENS="${OPENAI_COMPAT_MAX_TOKENS:-4096}"
export OPENAI_COMPAT_INCLUDE_REASONING="${OPENAI_COMPAT_INCLUDE_REASONING:-0}"
export OPENAI_COMPAT_TEMPERATURE="${OPENAI_COMPAT_TEMPERATURE:-0.2}"
exec "$SCRIPT_DIR/kilo.sh" "$@"
