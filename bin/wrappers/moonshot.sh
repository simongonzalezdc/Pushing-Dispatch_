#!/usr/bin/env bash
# moonshot.sh - Dispatch a Kimi (Moonshot) worker via Anthropic-compat endpoint.
#
# Kimi K2.6 is routed through Claude Code's harness using Moonshot's
# Anthropic-compatible API endpoint. --bare mode is used because
# third-party providers supply their own API keys.
#
# Kimi excels at long-context tasks (256K window) and mechanical refactors.
#
# API key: set MOONSHOT_API_KEY env var, or store in macOS Keychain
#          (service=pushing-dispatch, account=moonshot_api_key)
#
# Usage: moonshot.sh --task-file brief.md --cwd /path --worker-id w-xxxx-slug

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_exec.sh"

# Provider config
export CE_TOOL_NAME="kimi"
export CE_BARE_MODE=1  # Third-party: full Hybrid C (brief-only)

# Load API key
MOONSHOT_KEY=$(ce_load_api_key "pushing-dispatch" "moonshot_api_key" "MOONSHOT_API_KEY")
export ANTHROPIC_AUTH_TOKEN="$MOONSHOT_KEY"
export ANTHROPIC_BASE_URL="https://api.moonshot.ai/anthropic"
export ANTHROPIC_MODEL="${ANTHROPIC_MODEL:-kimi-k2.6}"

# Kimi thinking defaults
export CE_THINKING_TOKENS="${CE_THINKING_TOKENS:-0}"
export CE_MAX_TURNS="${CE_MAX_TURNS:-25}"

ce_parse_args "$@"
ce_run_claude
