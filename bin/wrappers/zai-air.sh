#!/usr/bin/env bash
# zai-air.sh - Fast Z.ai / GLM Air worker.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export ANTHROPIC_MODEL="${ANTHROPIC_MODEL:-glm-4.5-air}"
export CE_THINKING_TOKENS="${CE_THINKING_TOKENS:-8192}"

exec "$SCRIPT_DIR/zai.sh" "$@"
