#!/usr/bin/env bash
# unsloth-nucbox.sh — m3-class local executor via NUCBox dedicated agent qwen27 server (:8892).
# T02-B: dedicated always-qwen27 instance, separate from Studio, so the human UI cannot affect agents.
# Policy: bounded/localized/reversible/verifying only. Never architect/critic/security/vision/web.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_exec.sh"

export CE_TOOL_NAME="unsloth-nucbox"
export OPENAI_COMPAT_BASE_URL="${UNSLOTH_BASE_URL:-http://100.113.174.74:8892/v1}"
export OPENAI_COMPAT_PATH="${OPENAI_COMPAT_PATH:-/chat/completions}"
export OPENAI_COMPAT_MODEL="${UNSLOTH_MODEL:-unsloth/Qwen3.6-27B-MTP-GGUF}"
export OPENAI_COMPAT_API_KEY="${UNSLOTH_API_KEY:-local-unsloth}"
export OPENAI_COMPAT_MAX_TOKENS="${OPENAI_COMPAT_MAX_TOKENS:-8192}"
export OPENAI_COMPAT_TEMPERATURE="${OPENAI_COMPAT_TEMPERATURE:-0.2}"
export OPENAI_COMPAT_TIMEOUT="${OPENAI_COMPAT_TIMEOUT:-300}"
# T06 fix (code-review revised): reinforce the brief's OWN output protocol via the
# system role (more salient for a reasoning model than the same text buried in a long
# brief), WITHOUT re-stating or suppressing it. Enumerates ALL markers so NEEDS_GUIDANCE
# / BLOCKED are not silently forced to DONE. Grammar can't force the marker with thinking
# ON (verified on our build), so prompt saliency is the thinking-preserving lever.
export OPENAI_COMPAT_SYSTEM="${OPENAI_COMPAT_SYSTEM:-${UNSLOTH_SYSTEM:-You are an autonomous dispatch worker. Follow the dispatch output protocol defined in your task brief EXACTLY: end every response with the correct Status: marker on its own final line — Status: DONE, Status: DONE_WITH_CONCERNS, Status: NEEDS_GUIDANCE, or Status: BLOCKED — whichever the brief specifies for the situation. Never omit this final marker and never place text after it.}}"

ce_parse_args "$@"
ce_run_openai_compatible
