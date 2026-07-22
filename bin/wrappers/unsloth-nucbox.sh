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
export OPENAI_COMPAT_MAX_TOKENS="${OPENAI_COMPAT_MAX_TOKENS:-8192}"
export OPENAI_COMPAT_TEMPERATURE="${OPENAI_COMPAT_TEMPERATURE:-0.2}"
export OPENAI_COMPAT_TIMEOUT="${OPENAI_COMPAT_TIMEOUT:-300}"
# T06 fix: force the dispatch terminal-marker protocol (qwen27 doesn't reliably
# emit "Status: DONE" from the long brief alone). A firm system message is the
# thinking-preserving lever (grammar is dropped with thinking ON — verified on our build).
export OPENAI_COMPAT_SYSTEM="${UNSLOTH_SYSTEM:-You are an autonomous dispatch worker. MANDATORY OUTPUT PROTOCOL (non-negotiable): the VERY LAST line of every response must be exactly:
Status: DONE
Emit that exact line once the task is complete, with nothing after it. If you cannot complete the task, the last line must be exactly:
Status: DONE_WITH_CONCERNS
Never omit this marker and never place any text after it.}"

ce_parse_args "$@"
ce_run_openai_compatible
