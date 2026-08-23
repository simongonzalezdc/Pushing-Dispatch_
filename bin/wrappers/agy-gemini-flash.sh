#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_exec.sh"

export CE_TOOL_NAME="agy-gemini-flash"
export AGY_MODEL="${AGY_MODEL:-Gemini 3.7 Flash (Medium)}"  # CEO order 2026-08-22: medium-ONLY

ce_parse_args "$@"
ce_run_agy
