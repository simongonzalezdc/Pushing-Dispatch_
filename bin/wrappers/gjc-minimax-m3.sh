#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_exec.sh"
export CE_TOOL_NAME="minimax-m3"
export GJC_MODEL="${GJC_MODEL:-minimax-code/minimax-m3}"
ce_parse_args "$@"
ce_run_gjc
