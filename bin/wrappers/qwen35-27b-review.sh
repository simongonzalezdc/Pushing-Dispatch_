#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_exec.sh"

export CE_TOOL_NAME="qwen35-27b-review"
export NUC_WORKCELL_PROFILE="qwen35-27b-review"

ce_parse_args "$@"
ce_run_nuc_ondemand
