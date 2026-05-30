#!/usr/bin/env bash
# codex.sh - Dispatch a Codex worker through Codex CLI.
#
# Uses Codex's native non-interactive exec mode. Configure with:
#   CODEX_MODEL=gpt-5.1-codex
#   CODEX_SANDBOX=workspace-write
#   CODEX_APPROVAL_POLICY=never
#
# For local/Ollama execution, use the codex-oss executor or set:
#   CODEX_OSS=1 CODEX_LOCAL_PROVIDER=ollama

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_exec.sh"

export CE_TOOL_NAME="codex"
export CE_BARE_MODE=1

ce_parse_args "$@"

# Per-dispatch OpenAI account selection. The matrix sets CE_OPENAI_ACCOUNT
# (icloud/puenteworks/cerafica) per executor; each dispatch is a fresh
# subprocess so switching here takes effect without a session restart.
if [[ -n "${CE_OPENAI_ACCOUNT:-}" ]] && command -v codex-switch >/dev/null 2>&1; then
    codex-switch "$CE_OPENAI_ACCOUNT" >/dev/null 2>&1 || true
fi

ce_run_codex
