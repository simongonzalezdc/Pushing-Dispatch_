#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_exec.sh"

export CE_TOOL_NAME="grok-build"
# Official Grok Build model currently exposed by the authenticated CLI.
export GROK_MODEL="${GROK_MODEL:-grok-4.5}"

ce_parse_args "$@"
ce_run_grok
