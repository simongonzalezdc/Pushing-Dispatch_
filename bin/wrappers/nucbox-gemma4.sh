#!/usr/bin/env bash
# nucbox-gemma4.sh - NUCBox Ollama Gemma 4 12B fallback over OpenAI-compatible API.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_exec.sh"

export CE_TOOL_NAME="nucbox-gemma4"
export OPENAI_COMPAT_BASE_URL="${OPENAI_COMPAT_BASE_URL:-${NUCBOX_OLLAMA_OPENAI_BASE_URL:-${NUCBOX_GEMMA_BASE_URL:-http://100.113.174.74:11434/v1}}}"
export OPENAI_COMPAT_PATH="${OPENAI_COMPAT_PATH:-/chat/completions}"
export OPENAI_COMPAT_MODEL="${OPENAI_COMPAT_MODEL:-${NUCBOX_GEMMA_MODEL:-gemma4:12b}}"
export OPENAI_COMPAT_MAX_TOKENS="${OPENAI_COMPAT_MAX_TOKENS:-4096}"
export OPENAI_COMPAT_TEMPERATURE="${OPENAI_COMPAT_TEMPERATURE:-0.2}"
export OPENAI_COMPAT_THINK="${OPENAI_COMPAT_THINK:-false}"

ce_parse_args "$@"
if [[ "$CE_DRY_RUN" -eq 1 ]]; then
    export OPENAI_COMPAT_API_KEY="dry-run"
else
    # Ollama's OpenAI-compatible endpoint accepts any bearer token by default.
    export OPENAI_COMPAT_API_KEY="${OLLAMA_API_KEY:-${NUCBOX_OLLAMA_API_KEY:-ollama}}"
fi
ce_run_openai_compatible
