#!/usr/bin/env bash
# zai.sh - Z.ai / GLM 5.1 coding-plan worker.
#
# Uses Z.ai's OpenAI-compatible coding endpoint:
#   base URL: https://api.z.ai/api/coding/paas/v4
#   model:    glm-5.1 by default, override OPENAI_COMPAT_MODEL for variants
#   key:      Z_AI_API_KEY

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_exec.sh"

export CE_TOOL_NAME="zai"
export CE_BARE_MODE=1

export OPENAI_COMPAT_BASE_URL="${OPENAI_COMPAT_BASE_URL:-https://api.z.ai/api/coding/paas/v4}"
export OPENAI_COMPAT_PATH="${OPENAI_COMPAT_PATH:-/chat/completions}"
export OPENAI_COMPAT_MODEL="${OPENAI_COMPAT_MODEL:-glm-5.1}"
export OPENAI_COMPAT_MAX_TOKENS="${OPENAI_COMPAT_MAX_TOKENS:-8192}"
export OPENAI_COMPAT_TEMPERATURE="${OPENAI_COMPAT_TEMPERATURE:-0.2}"

export CE_THINKING_TOKENS="${CE_THINKING_TOKENS:-32768}"
export CE_MAX_TURNS="${CE_MAX_TURNS:-25}"

ce_parse_args "$@"
if [[ "$CE_DRY_RUN" -eq 1 ]]; then
    export OPENAI_COMPAT_API_KEY="dry-run"
else
    export OPENAI_COMPAT_API_KEY="$(ce_load_api_key "pushing-dispatch" "z_ai_api_key" "Z_AI_API_KEY")"
fi
ce_run_openai_compatible
