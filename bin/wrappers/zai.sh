#!/usr/bin/env bash
# zai.sh - LEGACY Dispatch worker: Z.AI GLM via Claude Code.
#
# Canonical agent invocation is ZCode (`zcode -p`). See docs/ZCODE.md.
# This wrapper still uses Z.ai's Anthropic-compatible endpoint so Claude Code
# supplies the tool loop for executor `zai-glm` until the lane is rewired.
#   base URL: https://api.z.ai/api/anthropic
#   model:    glm-5.3 by default, override ANTHROPIC_MODEL
#   key:      Z_AI_API_KEY

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_exec.sh"

export CE_TOOL_NAME="zai"
export CE_BARE_MODE=1

export ANTHROPIC_BASE_URL="${ANTHROPIC_BASE_URL:-https://api.z.ai/api/anthropic}"
export ANTHROPIC_MODEL="${ANTHROPIC_MODEL:-glm-5.3}"

export CE_THINKING_TOKENS="${CE_THINKING_TOKENS:-32768}"
export CE_MAX_TURNS="${CE_MAX_TURNS:-25}"

ce_parse_args "$@"
if [[ "$CE_DRY_RUN" -eq 1 ]]; then
    export ANTHROPIC_AUTH_TOKEN="dry-run"
else
    export ANTHROPIC_AUTH_TOKEN="$(ce_load_api_key "pushing-dispatch" "z_ai_api_key" "Z_AI_API_KEY")"
fi
ce_run_claude
