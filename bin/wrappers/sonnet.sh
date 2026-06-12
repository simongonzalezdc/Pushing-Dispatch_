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

# Drop inherited ANTHROPIC_* overrides and load the headless OAuth token
# (401s under provider-overridden environments, 2026-06-12).
ce_sanitize_anthropic_env

export ANTHROPIC_MODEL="${ANTHROPIC_MODEL:-claude-sonnet-4-6}"

ce_parse_args "$@"
ce_run_claude
