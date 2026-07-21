#!/usr/bin/env bash
# unsloth-nucbox.sh — m3-class local executor via NUCBox dedicated agent qwen27 server (:8892).
# T02-B: dedicated always-qwen27 instance, separate from Studio, so the human UI cannot affect agents.
# Policy: bounded/localized/reversible/verifying only. Never architect/critic/security/vision/web.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_exec.sh"

export CE_TOOL_NAME="unsloth-nucbox"
export OPENAI_COMPAT_BASE_URL="${UNSLOTH_BASE_URL:-http://100.113.174.74:8892/v1}"
export OPENAI_COMPAT_PATH="/chat/completions"
export OPENAI_COMPAT_MODEL="${UNSLOTH_MODEL:-unsloth/Qwen3.6-27B-MTP-GGUF}"
export OPENAI_COMPAT_API_KEY="${UNSLOTH_API_KEY:-local-unsloth}"
export OPENAI_COMPAT_MAX_TOKENS="${OPENAI_COMPAT_MAX_TOKENS:-4096}"
export OPENAI_COMPAT_TEMPERATURE="${OPENAI_COMPAT_TEMPERATURE:-0.2}"
export OPENAI_COMPAT_TIMEOUT="${OPENAI_COMPAT_TIMEOUT:-300}"

ce_parse_args "$@"
ce_run_openai_compatible
