#!/usr/bin/env bash
# DeepSeek V4 Pro through the Ollama Cloud subscription (same key as kimi-k3-ollama).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_exec.sh"

export CE_TOOL_NAME="deepseek-v4-pro"
export OPENAI_COMPAT_BASE_URL="https://ollama.com/v1"
export OPENAI_COMPAT_PATH="/chat/completions"
export OPENAI_COMPAT_MODEL="${DS_PRO_MODEL:-deepseek-v4-pro:0813}"
export OPENAI_COMPAT_MAX_TOKENS="${OPENAI_COMPAT_MAX_TOKENS:-131072}"
export OPENAI_COMPAT_TEMPERATURE="${OPENAI_COMPAT_TEMPERATURE:-0.2}"
export OPENAI_COMPAT_TIMEOUT="${OPENAI_COMPAT_TIMEOUT:-600}"

ce_parse_args "$@"
if [[ "$CE_DRY_RUN" -ne 1 ]]; then
    ds_key="${OLLAMA_API_KEY:-}"
    if [[ -z "$ds_key" ]]; then
        ds_key="$(ce_load_api_key "pushing-dispatch" "ollama_api_key" "OLLAMA_API_KEY" 2>/dev/null || true)"
    fi
    if [[ -z "$ds_key" ]]; then
        echo "Error: Ollama Cloud key not found." >&2
        exit 1
    fi
    export OPENAI_COMPAT_API_KEY="$ds_key"
fi
ce_run_openai_compatible
