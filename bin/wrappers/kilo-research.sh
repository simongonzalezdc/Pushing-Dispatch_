#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export CE_TOOL_NAME="kilo-research"
export OPENAI_COMPAT_MODEL="${OPENAI_COMPAT_MODEL:-perplexity/sonar-pro-search}"
export OPENAI_COMPAT_REASONING_EFFORT="${OPENAI_COMPAT_REASONING_EFFORT:-medium}"
exec "$SCRIPT_DIR/kilo.sh" "$@"
