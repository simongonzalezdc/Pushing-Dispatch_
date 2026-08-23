#!/usr/bin/env bash
# nucbox-champion.sh — Qwen3.8-27B on the NUC (co-resident with Ornith on :46381).
# Zero-cost local lane: certified delegation card, 262k ctx, 54x prompt cache.
# Best for: agent tool loops, code, terse factual output. ~26 tok/s prose.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_exec.sh"

export CE_TOOL_NAME="nucbox-champion"
export OPENAI_COMPAT_BASE_URL="${CHAMPION_BASE_URL:-http://100.113.174.74:46380/v1}"
export OPENAI_COMPAT_PATH="/chat/completions"
export OPENAI_COMPAT_MODEL="${CHAMPION_MODEL:-Qwen3.8-27B}"
export OPENAI_COMPAT_EXPECT_RESPONSE_MODEL="$OPENAI_COMPAT_MODEL"
export OPENAI_COMPAT_MAX_TOKENS="${CHAMPION_MAX_TOKENS:-8192}"
export OPENAI_COMPAT_TEMPERATURE="${CHAMPION_TEMPERATURE:-0.2}"

ce_parse_args "$@"
export OPENAI_COMPAT_API_KEY="${CHAMPION_API_KEY:-local-no-key}"

# Gen canary: model-identity assertion (COO-004 fix)
export CE_GEN_CANARY_URL="$OPENAI_COMPAT_BASE_URL/chat/completions"
export CE_GEN_CANARY_MODEL="$OPENAI_COMPAT_MODEL"

ce_run_openai_compatible "$@"
