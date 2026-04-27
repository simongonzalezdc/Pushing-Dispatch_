#!/usr/bin/env bash
# deepseek.sh - Dispatch a DeepSeek worker via Anthropic-compat endpoint.
#
# DeepSeek is routed through Claude Code's harness using DeepSeek's
# Anthropic-compatible API endpoint. --bare mode for brief-only context.
#
# DeepSeek excels at pure-code tasks with strong type/test signals.
#
# API key: set DEEPSEEK_API_KEY env var, or store in macOS Keychain
#          (service=pushing-dispatch, account=deepseek_api_key)
#
# Usage: deepseek.sh --task-file brief.md --cwd /path --worker-id w-xxxx-slug

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_exec.sh"

# Provider config
export CE_TOOL_NAME="deepseek"
export CE_BARE_MODE=1

# Load API key
DEEPSEEK_KEY=$(ce_load_api_key "pushing-dispatch" "deepseek_api_key" "DEEPSEEK_API_KEY")
export ANTHROPIC_AUTH_TOKEN="$DEEPSEEK_KEY"
export ANTHROPIC_BASE_URL="https://api.deepseek.com/anthropic"
export ANTHROPIC_MODEL="${ANTHROPIC_MODEL:-deepseek-v4-flash}"

# DeepSeek defaults
export CE_THINKING_TOKENS="${CE_THINKING_TOKENS:-4000}"
export CE_MAX_TURNS="${CE_MAX_TURNS:-25}"

ce_parse_args "$@"
ce_run_claude
