#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_exec.sh"

export CE_TOOL_NAME="kimi-k27"
# Kimi CLI's managed alias; the service controls the underlying K2.7 revision.
export KIMI_MODEL="${KIMI_MODEL:-kimi-code/kimi-for-coding}"

ce_parse_args "$@"
ce_run_kimi
