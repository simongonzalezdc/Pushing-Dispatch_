#!/usr/bin/env bash
# nucbox-ornith.sh — Ornith-1.5-35B-A3B APEX on the NUC (:46381 forwarder).
# Zero-cost local speed lane: ~55 tok/s decode (2x champion), thinking-on.
# Best for: volume generation, math with thinking, long analysis.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_exec.sh"

export CE_TOOL_NAME="nucbox-ornith"
export OPENAI_COMPAT_BASE_URL="${ORNITH_BASE_URL:-http://100.113.174.74:46381/v1}"
export OPENAI_COMPAT_PATH="/chat/completions"
export OPENAI_COMPAT_MODEL="${ORNITH_MODEL:-Ornith-1.5-35B}"
export OPENAI_COMPAT_EXPECT_RESPONSE_MODEL="$OPENAI_COMPAT_MODEL"
export OPENAI_COMPAT_MAX_TOKENS="${ORNITH_MAX_TOKENS:-8192}"
export OPENAI_COMPAT_TEMPERATURE="${ORNITH_TEMPERATURE:-0.2}"

ce_parse_args "$@"
export OPENAI_COMPAT_API_KEY="${ORNITH_API_KEY:-local-no-key}"

export CE_GEN_CANARY_URL="$OPENAI_COMPAT_BASE_URL/chat/completions"
export CE_GEN_CANARY_MODEL="$OPENAI_COMPAT_MODEL"

ce_run_openai_compatible "$@"
