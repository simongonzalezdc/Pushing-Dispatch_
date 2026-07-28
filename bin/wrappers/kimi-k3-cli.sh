#!/usr/bin/env bash
# Kimi K3 through the user's official Kimi CLI subscription session.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_exec.sh"

export CE_TOOL_NAME="kimi-k3-cli"
export KIMI_MODEL="${KIMI_MODEL:-kimi-code/k3}"

ce_parse_args "$@"
ce_run_kimi
