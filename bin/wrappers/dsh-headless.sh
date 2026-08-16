#!/usr/bin/env bash
# DeepSeek Harness (dsh) one-shot lane. Model and provider come from
# ~/.dsh/settings.yaml (default: deepseek-v4-flash, provider deepseek-official).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_exec.sh"

export CE_TOOL_NAME="dsh"

ce_parse_args "$@"
ce_run_dsh
