#!/usr/bin/env bash
# Xiaomi MiMo — monthly sub (CEO reactivated 2026-08-25 after payment; use-it window).
# Key lives in Keychain (service=pushing-dispatch, account=xiaomi_api_key) —
# refreshed there on 2026-08-25 via clipboard intake; never in env files.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_exec.sh"
export CE_TOOL_NAME="xiaomi-mimo"
export OPENAI_COMPAT_BASE_URL="${XIAOMI_BASE_URL:-https://api.xiaomimimo.com/v1}"
export OPENAI_COMPAT_MODEL="${XIAOMI_MODEL:-mimo-v2-pro}"

if [[ -z "${XIAOMI_API_KEY:-}" ]]; then
  XIAOMI_API_KEY="$(security find-generic-password -s pushing-dispatch -a xiaomi_api_key -w 2>/dev/null || true)"
  export XIAOMI_API_KEY
fi
if [[ -z "${XIAOMI_API_KEY:-}" ]]; then
  echo "xiaomi-mimo: no API key (Keychain pushing-dispatch/xiaomi_api_key) — run the clipboard intake" >&2
  exit 3
fi
export OPENAI_COMPAT_API_KEY="$XIAOMI_API_KEY"

ce_run_openai_compatible "$@"
