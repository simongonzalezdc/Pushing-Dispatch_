#!/usr/bin/env bash
# DeepInfra — CEO 2026-08-30: "$40 budget total, all used for
# deepseek-ai/DeepSeek-V4-Flash-0731" (https://deepinfra.com/dash/models/
# details?model=deepseek-ai%2FDeepSeek-V4-Flash-0731). Server reports exact
# per-call USD as usage.estimated_cost; the $40 hard cap lives in sinter's
# provider-budgets ledger (~/.sinter/provider-budgets.json) and fail-closes
# this host. ONLY the earmarked model may ride this lane.
# Key lives in Keychain (service=pushing-dispatch, account=deepinfra_api_key).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_exec.sh"
export CE_TOOL_NAME="deepinfra"
export OPENAI_COMPAT_BASE_URL="${DEEPINFRA_BASE_URL:-https://api.deepinfra.com/v1/openai}"
export OPENAI_COMPAT_AUTH_STYLE="bearer"
export OPENAI_COMPAT_MODEL="${DEEPINFRA_MODEL:-deepseek-ai/DeepSeek-V4-Flash-0731}"

if [[ -z "${DEEPINFRA_API_KEY:-}" ]]; then
  DEEPINFRA_API_KEY="$(security find-generic-password -s pushing-dispatch -a deepinfra_api_key -w 2>/dev/null || true)"
  export DEEPINFRA_API_KEY
fi
if [[ -z "${DEEPINFRA_API_KEY:-}" ]]; then
  echo "deepinfra: no API key (Keychain pushing-dispatch/deepinfra_api_key)" >&2
  exit 3
fi
export OPENAI_COMPAT_API_KEY="$DEEPINFRA_API_KEY"

ce_run_openai_compatible "$@"
