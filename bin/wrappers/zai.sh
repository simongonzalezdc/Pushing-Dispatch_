#!/usr/bin/env bash
# zai.sh - Manifest-compatible Z.ai / GLM worker.
#
# Mirrors Manifest's Z.ai/custom GLM Anthropic-compatible routes:
#   base URL: https://api.z.ai/api/anthropic
#   model:    glm-5.1 by default, override ANTHROPIC_MODEL for glm-4.5-air
#   key:      Z_AI_API_KEY

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_exec.sh"

export CE_TOOL_NAME="zai"
export CE_BARE_MODE=1

export ANTHROPIC_BASE_URL="https://api.z.ai/api/anthropic"
export ANTHROPIC_MODEL="${ANTHROPIC_MODEL:-glm-5.1}"

export CE_THINKING_TOKENS="${CE_THINKING_TOKENS:-32768}"
export CE_MAX_TURNS="${CE_MAX_TURNS:-25}"

ce_parse_args "$@"
if [[ "$CE_DRY_RUN" -eq 1 ]]; then
    export ANTHROPIC_AUTH_TOKEN="dry-run"
else
    export ANTHROPIC_AUTH_TOKEN="$(ce_load_api_key "pushing-dispatch" "z_ai_api_key" "Z_AI_API_KEY")"
fi
ce_run_claude
