#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_exec.sh"

export CE_TOOL_NAME="higgsfield-media"
export CE_PROVIDER="higgsfield"
export CE_MODEL="${CE_MODEL:-veo3_1}"          # default video model; override per task
export CE_CLASS="media-generation"              # not a text/coding lane
export CE_LANE_KIND="subscription"

# --- CREDIT EXHAUSTION NOTICE (CEO-mandated 2026-08-20) ---
# If credits hit zero, the CLI/API stops working. The ACCOUNT DOES NOT DIE.
# Simon can still use Higgsfield on the WEBSITE (higgsfield.ai) with the same
# paid plan — the CLI credits are a separate meter from the web interface.
# When this happens: report "credits exhausted — website still available at
# higgsfield.ai" to the caller + log the event; do NOT route around it.
_check_credits() {
  local bal
  bal=$(higgsfield account status 2>/dev/null | grep -oE '[0-9]+\.[0-9]+ credits' | cut -d' ' -f1)
  if [ -n "$bal" ] && python3 -c "exit(0 if float('$bal') < 50 else 1)" 2>/dev/null; then
    echo "⚠️  HIGGSFIELD CREDITS LOW (${bal} remaining). When they run out:" >&2
    echo "   → The CLI stops generating." >&2
    echo "   → The paid account on higgsfield.ai (website) still works — same plan, separate meter." >&2
    echo "   → Top up or generate on the web until credits are replenished." >&2
  fi
}
_check_credits

exec "$@"
