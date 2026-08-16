#!/usr/bin/env bash
# Kimi K3 through the SECOND Kimi Code subscription (API-key account,
# keychain pushing-dispatch/kimi_api_key). Same CLI as kimi-k3-cli but a
# separate account — run lanes in parallel while both subscriptions are live.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_exec.sh"

export CE_TOOL_NAME="kimi-k3-key"
export KIMI_MODEL="${KIMI_MODEL:-kimi-code/k3}"

ce_parse_args "$@"
if [[ "$CE_DRY_RUN" -ne 1 ]] && [[ -z "${KIMI_API_KEY:-}" ]]; then
    secret="$(ce_load_api_key "pushing-dispatch" "kimi_api_key" "KIMI_API_KEY" 2>/dev/null || true)"
    if [[ -z "$secret" ]]; then
        echo "Error: kimi_api_key not found." >&2
        exit 1
    fi
    export KIMI_API_KEY="$secret"
fi
ce_run_kimi
