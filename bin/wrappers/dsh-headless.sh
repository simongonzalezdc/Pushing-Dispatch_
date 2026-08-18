#!/usr/bin/env bash
# DeepSeek Harness (dsh) one-shot lane. Model and provider come from
# DSH_HOME/settings.yaml — Wave-0 T6 fix (2026-08-17): we pin DSH_HOME to the
# dispatch-owned home so the lane serves its configured model (flash) and never
# drifts with interactive ~/.dsh settings. Override by exporting DSH_HOME first.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_exec.sh"

export CE_TOOL_NAME="dsh"
export DSH_HOME="${DSH_HOME:-$HOME/.local/share/pushing-dispatch/dsh-home}"

ce_parse_args "$@"
ce_run_dsh
