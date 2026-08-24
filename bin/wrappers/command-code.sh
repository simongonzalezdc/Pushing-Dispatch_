#!/usr/bin/env bash
# Command Code (commandcode.ai) through the user's authenticated CLI session (Pro plan credits).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_exec.sh"

export CE_TOOL_NAME="command-code"
export COMMANDCODE_MODEL="${COMMANDCODE_MODEL:-deepseek/deepseek-v4-flash}"

ce_parse_args "$@"
ce_run_commandcode
