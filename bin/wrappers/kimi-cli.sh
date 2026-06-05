#!/usr/bin/env bash
# kimi-cli.sh - Dispatch through local Kimi Code CLI OAuth login.
#
# This uses the Kimi CLI credential store under ~/.kimi. It does not require
# MOONSHOT_API_KEY and does not read provider keys from this repository.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_exec.sh"

export CE_TOOL_NAME="kimi-cli"
export KIMI_MODEL="${KIMI_MODEL:-kimi-code/kimi-for-coding}"

ce_parse_args "$@"
ce_run_kimi_cli
