#!/usr/bin/env bash
# Dell XPS GPU worker — Qwen3.5-2B local inference via Ollama.
#
# Cascade pattern: this is the FIRST executor for trivial tasks.
# If the 2B produces a low-quality output (refusal, empty, or
# too-short), the wrapper exits non-zero → lane_health demotes it
# → next dispatch routes to the cloud fallback automatically.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_exec.sh"

export CE_TOOL_NAME="ollama-xps-gpu"
export OPENAI_COMPAT_BASE_URL="${XPS_OLLAMA_BASE_URL:-http://100.74.110.12:11434/v1}"
export OPENAI_COMPAT_PATH="/chat/completions"
export OPENAI_COMPAT_MODEL="${XPS_OLLAMA_MODEL:-qwen35-2b-max}"
export OPENAI_COMPAT_EXPECT_RESPONSE_MODEL="$OPENAI_COMPAT_MODEL"
export OPENAI_COMPAT_API_KEY="${XPS_OLLAMA_API_KEY:-ollama-tailnet}"
export OPENAI_COMPAT_MAX_TOKENS="${OPENAI_COMPAT_MAX_TOKENS:-4096}"
export OPENAI_COMPAT_TEMPERATURE="${OPENAI_COMPAT_TEMPERATURE:-0.2}"
export OPENAI_COMPAT_TIMEOUT="${OPENAI_COMPAT_TIMEOUT:-120}"
# Disable thinking mode for faster trivial responses
export OPENAI_COMPAT_EXTRA_BODY="${OPENAI_COMPAT_EXTRA_BODY:-{\"chat_template_kwargs\":{\"enable_thinking\":false}}}"

ce_parse_args "$@"
ce_run_openai_compatible
