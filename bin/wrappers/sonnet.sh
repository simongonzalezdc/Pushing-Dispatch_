#!/usr/bin/env bash
# sonnet.sh - Dispatch a Claude Sonnet worker via Anthropic API.
#
# This is the default executor for most tasks. Sonnet runs through
# the standard Claude Code harness (not --bare) because Anthropic
# providers may use subscription OAuth.
#
# Usage: sonnet.sh --task-file brief.md --cwd /path/to/project --worker-id w-xxxx-slug

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_exec.sh"

# Provider config
export CE_TOOL_NAME="sonnet"
export CE_BARE_MODE=0  # Anthropic providers keep normal mode (subscription OAuth)

# Anthropic lanes must hit the real API with subscription OAuth. The
# dispatching session often carries ANTHROPIC_* overrides (proxy base URLs,
# foreign auth tokens) that silently route OAuth creds to the wrong endpoint
# (401 Invalid authentication credentials, 2026-06-12). Drop them.
unset ANTHROPIC_BASE_URL ANTHROPIC_AUTH_TOKEN ANTHROPIC_API_KEY

export ANTHROPIC_MODEL="${ANTHROPIC_MODEL:-claude-sonnet-4-6}"

ce_parse_args "$@"
ce_run_claude
