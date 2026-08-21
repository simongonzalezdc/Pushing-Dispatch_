#!/usr/bin/env bash
# DeepSeek Harness (dsh) one-shot lane. Model and provider come from
# DSH_HOME/settings.yaml — Wave-0 T6 fix (2026-08-17): we pin DSH_HOME to the
# dispatch-owned home so the lane serves its configured model (flash) and never
# drifts with interactive ~/.dsh settings. Override by exporting DSH_HOME first.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_exec.sh"

# DeepSeek credential: dsh's deepseek-official route needs DEEPSEEK_API_KEY.
# Read it from the locked-down Hermes dotenv (same allowlist pattern as
# read-hermes-zai-key) unless the launching environment already provides one.
if [[ -z "${DEEPSEEK_API_KEY:-}" ]]; then
    _dsk="$("$SCRIPT_DIR/../read-hermes-deepseek-key" 2>/dev/null || true)"
    # keychain direct read (S-080): works outside login shells
    [[ -n "${_dsk:-}" ]] || _dsk="$(security find-generic-password -s pushing-dispatch -a deepseek_api_key -w 2>/dev/null || true)"
    [[ -z "$_dsk" ]] || export DEEPSEEK_API_KEY="$_dsk"
    unset _dsk
fi

export CE_TOOL_NAME="dsh"
export DSH_HOME="${DSH_HOME:-$HOME/.local/share/pushing-dispatch/dsh-home}"

ce_parse_args "$@"
ce_run_dsh
