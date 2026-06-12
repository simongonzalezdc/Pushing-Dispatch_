#!/usr/bin/env bash
# gemini.sh - Dispatch through Google Gemini API-key generateContent.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_exec.sh"

export CE_TOOL_NAME="${CE_TOOL_NAME:-gemini}"
export GEMINI_MODEL="${GEMINI_MODEL:-gemini-3.1-pro-preview}"

ce_parse_args "$@"

# Gemini lanes are single-shot generateContent calls with no tool loop. In
# task/breakout mode they used to emit one response and finalize "done" with
# turns_taken=0 — a silent no-op that looked like success (2026-06-12).
# The matrix marks these lanes consult-only; fail loudly if routed otherwise.
if [[ "$CE_MODE" != "consult" ]]; then
    echo "gemini lanes are consult-only (single-shot generateContent, no tool loop); got mode=$CE_MODE" >&2
    ce_finalize_status "errored" 4 "gemini lane is consult-only; got mode=$CE_MODE"
    exit 4
fi

if [[ "$CE_DRY_RUN" -eq 1 ]]; then
    export GEMINI_API_KEY_EFFECTIVE="dry-run"
elif [[ -n "${GEMINI_API_KEY:-}" ]]; then
    export GEMINI_API_KEY_EFFECTIVE="$GEMINI_API_KEY"
elif [[ -n "${GOOGLE_API_KEY:-}" ]]; then
    export GEMINI_API_KEY_EFFECTIVE="$GOOGLE_API_KEY"
else
    export GEMINI_API_KEY_EFFECTIVE="$(ce_load_api_key "pushing-dispatch" "gemini_api_key" "GEMINI_API_KEY")"
fi

export GEMINI_MAX_TOKENS="${GEMINI_MAX_TOKENS:-32768}"

ce_run_gemini
