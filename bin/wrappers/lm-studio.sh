#!/usr/bin/env bash
# lm-studio.sh - NUC LiteLLM/LM Studio over OpenAI-compatible API.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_exec.sh"

export CE_TOOL_NAME="lm-studio"
export OPENAI_COMPAT_BASE_URL="${OPENAI_COMPAT_BASE_URL:-${LM_STUDIO_BASE_URL:-${LMSTUDIO_BASE_URL:-${FACTORY_SELF_HOSTED_INFERENCE_URL:-${LOCAL_BASE_URL:-http://127.0.0.1:4000/v1}}}}}"
export OPENAI_COMPAT_PATH="${OPENAI_COMPAT_PATH:-/chat/completions}"
export OPENAI_COMPAT_MODEL="${OPENAI_COMPAT_MODEL:-${LM_STUDIO_MODEL:-${LMSTUDIO_MODEL:-${LOCAL_MODEL:-qwen3.6-35b-a3b-mtp}}}}"
export OPENAI_COMPAT_MAX_TOKENS="${OPENAI_COMPAT_MAX_TOKENS:-8192}"
export OPENAI_COMPAT_TEMPERATURE="${OPENAI_COMPAT_TEMPERATURE:-0.2}"

ce_parse_args "$@"
if [[ "$CE_DRY_RUN" -eq 1 ]]; then
    export OPENAI_COMPAT_API_KEY="dry-run"
else
    export OPENAI_COMPAT_API_KEY="${LM_STUDIO_API_KEY:-${LMSTUDIO_API_KEY:-${LOCAL_API_KEY:-${PIPELINE_LOCAL_LLM_API_KEY:-${FACTORY_SELF_HOSTED_INFERENCE_API_KEY:-${LITELLM_API_KEY:-}}}}}}"
    if [[ -z "$OPENAI_COMPAT_API_KEY" ]]; then
        export OPENAI_COMPAT_API_KEY="$(ce_load_api_key "pushing-dispatch" "local_api_key" "LOCAL_API_KEY" 2>/dev/null || true)"
    fi
    if [[ -z "$OPENAI_COMPAT_API_KEY" ]]; then
        export OPENAI_COMPAT_API_KEY="$(ce_load_api_key "pushing-dispatch" "pipeline_local_llm_api_key" "PIPELINE_LOCAL_LLM_API_KEY" 2>/dev/null || true)"
    fi
    if [[ -z "$OPENAI_COMPAT_API_KEY" ]]; then
        echo "Error: local LM Studio key not found. Set LOCAL_API_KEY or PIPELINE_LOCAL_LLM_API_KEY." >&2
        exit 1
    fi
fi
ce_run_openai_compatible
