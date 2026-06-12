#!/usr/bin/env bash
# haiku.sh - Dispatch a Claude Haiku worker via Anthropic API.
#
# Haiku is the leaf executor tier. Fast, cheap, good for trivial
# tasks like lint fixes, single-file edits, simple queries.
# Haiku cannot dispatch sub-workers (leaf executor).
#
# Usage: haiku.sh --task-file brief.md --cwd /path --worker-id w-xxxx-slug

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_exec.sh"

# Provider config
export CE_TOOL_NAME="haiku"
export CE_BARE_MODE=0

# Drop inherited ANTHROPIC_* overrides and load the headless OAuth token
# (401s under provider-overridden environments, 2026-06-12).
ce_sanitize_anthropic_env

export ANTHROPIC_MODEL="${ANTHROPIC_MODEL:-claude-haiku-4-5-20251001}"
export CE_THINKING_TOKENS=0  # Haiku: no extended thinking

ce_parse_args "$@"
ce_run_claude
