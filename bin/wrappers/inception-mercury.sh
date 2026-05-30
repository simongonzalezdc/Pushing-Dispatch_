#!/usr/bin/env bash
# inception-mercury.sh - Inception Labs Mercury-2 via OpenAI-compatible API.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_exec.sh"

export CE_TOOL_NAME="inception-mercury"
export OPENAI_COMPAT_BASE_URL="${OPENAI_COMPAT_BASE_URL:-https://api.inceptionlabs.ai/v1}"
export OPENAI_COMPAT_PATH="${OPENAI_COMPAT_PATH:-/chat/completions}"
export OPENAI_COMPAT_MODEL="${OPENAI_COMPAT_MODEL:-Mercury-2}"
export OPENAI_COMPAT_MAX_TOKENS="${OPENAI_COMPAT_MAX_TOKENS:-8192}"
export OPENAI_COMPAT_TEMPERATURE="${OPENAI_COMPAT_TEMPERATURE:-0.2}"

ce_parse_args "$@"
if [[ "$CE_DRY_RUN" -eq 1 ]]; then
    export OPENAI_COMPAT_API_KEY="dry-run"
else
    export OPENAI_COMPAT_API_KEY="$(ce_load_api_key "pushing-dispatch" "custom_inception_api_key" "CUSTOM_INCEPTION_API_KEY")"
fi
ce_run_openai_compatible
