#!/usr/bin/env bash
# kilo.sh - Dispatch through Kilo Gateway's OpenAI-compatible API.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_exec.sh"

export CE_TOOL_NAME="${CE_TOOL_NAME:-kilo}"
export OPENAI_COMPAT_BASE_URL="${OPENAI_COMPAT_BASE_URL:-https://api.kilo.ai/api/gateway}"
export OPENAI_COMPAT_PATH="${OPENAI_COMPAT_PATH:-/chat/completions}"
export OPENAI_COMPAT_MODEL="${OPENAI_COMPAT_MODEL:-kilo-auto/balanced}"
export OPENAI_COMPAT_MAX_TOKENS="${OPENAI_COMPAT_MAX_TOKENS:-32768}"
export OPENAI_COMPAT_INCLUDE_REASONING="${OPENAI_COMPAT_INCLUDE_REASONING:-1}"

ce_parse_args "$@"
if [[ "$CE_DRY_RUN" -eq 1 ]]; then
    export OPENAI_COMPAT_API_KEY="dry-run"
else
    export OPENAI_COMPAT_API_KEY="$(ce_load_api_key "pushing-dispatch" "kilo_api_key" "KILO_API_KEY")"
fi
ce_run_openai_compatible
