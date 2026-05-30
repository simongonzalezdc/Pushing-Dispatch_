#!/usr/bin/env bash
# lm-studio.sh - LM Studio over Tailscale via OpenAI-compatible API.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_exec.sh"

export CE_TOOL_NAME="lm-studio"
export OPENAI_COMPAT_BASE_URL="${OPENAI_COMPAT_BASE_URL:-http://100.66.225.85:1234/v1}"
export OPENAI_COMPAT_PATH="${OPENAI_COMPAT_PATH:-/chat/completions}"
export OPENAI_COMPAT_MODEL="${OPENAI_COMPAT_MODEL:-qwen3-coder-next-reap-40b-a3b-i1}"
export OPENAI_COMPAT_MAX_TOKENS="${OPENAI_COMPAT_MAX_TOKENS:-8192}"
export OPENAI_COMPAT_TEMPERATURE="${OPENAI_COMPAT_TEMPERATURE:-0.2}"

ce_parse_args "$@"
if [[ "$CE_DRY_RUN" -eq 1 ]]; then
    export OPENAI_COMPAT_API_KEY="dry-run"
else
    export OPENAI_COMPAT_API_KEY="$(ce_load_api_key "pushing-dispatch" "openai_api_key" "OPENAI_API_KEY")"
fi
ce_run_openai_compatible
