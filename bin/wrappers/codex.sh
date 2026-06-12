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
# (icloud/puenteworks/cerafica) per executor.
#
# Preferred: a per-account CODEX_HOME under ~/.codex-dispatch/<account>, each
# with its own self-rotating OAuth login. The legacy codex-switch path copied
# a STATIC auth snapshot over the shared ~/.codex/auth.json; codex refresh
# tokens are single-use and snapshots are never re-saved after rotation, so
# every switch stomped fresh credentials with consumed ones and locked out
# all newly spawned codex processes (2026-06-12 lockouts, twice). Dispatch
# homes isolate token lineages from interactive sessions and from each other.
# Fallback to codex-switch only when no dispatch home exists for the account.
if [[ -n "${CE_OPENAI_ACCOUNT:-}" && -f "$HOME/.codex-dispatch/$CE_OPENAI_ACCOUNT/auth.json" ]]; then
    export CODEX_HOME="$HOME/.codex-dispatch/$CE_OPENAI_ACCOUNT"
elif [[ -n "${CE_OPENAI_ACCOUNT:-}" ]] && command -v codex-switch >/dev/null 2>&1; then
    codex-switch "$CE_OPENAI_ACCOUNT" >/dev/null 2>&1 || true
fi

ce_run_codex
