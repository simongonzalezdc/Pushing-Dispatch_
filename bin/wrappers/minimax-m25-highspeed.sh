#!/usr/bin/env bash
# minimax-m25-highspeed.sh - MiniMax M2.5 highspeed coding-plan lane.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export CE_TOOL_NAME="minimax-m25-highspeed"
export ANTHROPIC_MODEL="${ANTHROPIC_MODEL:-MiniMax-M2.5-highspeed}"
exec "$SCRIPT_DIR/minimax-m25.sh" "$@"
