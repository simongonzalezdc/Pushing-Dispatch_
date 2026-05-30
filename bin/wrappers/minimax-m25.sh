#!/usr/bin/env bash
# minimax-m25.sh - MiniMax M2.5 Anthropic-compatible coding-plan lane.
# International Coding Plan endpoint: https://api.minimax.io/anthropic
# (China endpoint is https://api.minimaxi.com/anthropic — do NOT use for intl plan)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_exec.sh"

export CE_TOOL_NAME="minimax-m25"
export CE_BARE_MODE=1

export ANTHROPIC_BASE_URL="${ANTHROPIC_BASE_URL:-https://api.minimax.io/anthropic}"
export ANTHROPIC_MODEL="${ANTHROPIC_MODEL:-MiniMax-M2.5}"

export CE_THINKING_TOKENS="${CE_THINKING_TOKENS:-0}"
export CE_MAX_TURNS="${CE_MAX_TURNS:-25}"

ce_parse_args "$@"
if [[ "$CE_DRY_RUN" -eq 1 ]]; then
    export ANTHROPIC_AUTH_TOKEN="dry-run"
else
    export ANTHROPIC_AUTH_TOKEN="$(ce_load_api_key "pushing-dispatch" "minimax_api_key" "MINIMAX_API_KEY")"
fi
ce_run_claude
