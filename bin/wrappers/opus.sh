#!/usr/bin/env bash
# opus.sh - Dispatch a Claude Opus worker via Anthropic API.
#
# Opus is the orchestrator tier. Used for synthesis, planning,
# and complex multi-step tasks. Supports thinking token tiers
# via --thinking flag.
#
# Usage: opus.sh --task-file brief.md --cwd /path --worker-id w-xxxx-slug [--thinking 8000]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_exec.sh"

# Provider config
export CE_TOOL_NAME="opus"
export CE_BARE_MODE=0

# Drop inherited ANTHROPIC_* overrides and load the headless OAuth token
# (401s under provider-overridden environments, 2026-06-12).
ce_sanitize_anthropic_env

export ANTHROPIC_MODEL="${ANTHROPIC_MODEL:-claude-opus-4-8}"

# Opus supports higher thinking token budgets
export CE_THINKING_TOKENS="${CE_THINKING_TOKENS:-4000}"

ce_parse_args "$@"
ce_run_claude
