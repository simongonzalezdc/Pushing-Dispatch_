#!/usr/bin/env bash
# kimi-coding.sh - Manifest-compatible Kimi Coding worker.
#
# Mirrors Manifest's Kimi Coding custom provider:
#   base URL: https://api.kimi.com/coding
#   model:    kimi-for-coding
#   key:      KIMI_API_KEY

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_exec.sh"

export CE_TOOL_NAME="kimi-coding"
export CE_BARE_MODE=1

export ANTHROPIC_BASE_URL="https://api.kimi.com/coding"
export ANTHROPIC_MODEL="${ANTHROPIC_MODEL:-kimi-for-coding}"

export CE_THINKING_TOKENS="${CE_THINKING_TOKENS:-0}"
export CE_MAX_TURNS="${CE_MAX_TURNS:-25}"

ce_parse_args "$@"
if [[ "$CE_DRY_RUN" -eq 1 ]]; then
    export ANTHROPIC_AUTH_TOKEN="dry-run"
else
    export ANTHROPIC_AUTH_TOKEN="$(ce_load_api_key "pushing-dispatch" "kimi_api_key" "KIMI_API_KEY")"
fi
ce_run_claude
