#!/usr/bin/env bash
# Kimi K3 through the user's Ollama Cloud subscription. Never reads Kimi auth.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_exec.sh"

export CE_TOOL_NAME="kimi-k3-ollama"
export OPENAI_COMPAT_BASE_URL="https://ollama.com/v1"
export OPENAI_COMPAT_PATH="/chat/completions"
export OPENAI_COMPAT_MODEL="${OLLAMA_KIMI_K3_MODEL:-kimi-k3}"
export OPENAI_COMPAT_MAX_TOKENS="${OPENAI_COMPAT_MAX_TOKENS:-131072}"
export OPENAI_COMPAT_TEMPERATURE="${OPENAI_COMPAT_TEMPERATURE:-0.2}"
export OPENAI_COMPAT_TIMEOUT="${OPENAI_COMPAT_TIMEOUT:-600}"

ce_parse_args "$@"
if [[ "$CE_DRY_RUN" -eq 1 ]]; then
    export OPENAI_COMPAT_API_KEY="dry-run"
else
    export OPENAI_COMPAT_API_KEY="${OLLAMA_API_KEY:-}"
    if [[ -z "$OPENAI_COMPAT_API_KEY" ]]; then
        export OPENAI_COMPAT_API_KEY="$(ce_load_api_key "pushing-dispatch" "ollama_api_key" "OLLAMA_API_KEY" 2>/dev/null || true)"
    fi
    if [[ -z "$OPENAI_COMPAT_API_KEY" ]]; then
        echo "Error: Ollama Cloud key not found. Kimi subscription credentials are intentionally unsupported." >&2
        exit 1
    fi
fi
ce_run_openai_compatible
