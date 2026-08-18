#!/usr/bin/env bash
# Kimi K3 through the DYING subscription (info@kyanitelabs.tech, keychain
# pushing-dispatch/kimi_api_key_kyanite). Bias routing HERE first while its
# quota lasts; simon@puenteworks lanes are the survivors/fallback.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_exec.sh"

export CE_TOOL_NAME="kimi-k3-kyanite"
export KIMI_MODEL="${KIMI_MODEL:-kimi-code/k3}"

ce_parse_args "$@"
if [[ "$CE_DRY_RUN" -ne 1 ]] && [[ -z "${KIMI_API_KEY:-}" ]]; then
    secret="$(ce_load_api_key "pushing-dispatch" "kimi_api_key_kyanite" "KIMI_API_KEY" 2>/dev/null || true)"
    if [[ -z "$secret" ]]; then
        echo "Error: kimi_api_key_kyanite not found." >&2
        exit 1
    fi
    export KIMI_API_KEY="$secret"
fi
ce_run_kimi
