#!/usr/bin/env bash
# MiniMax-M3 via GJC — load key from env/hermes/sinter first (no Keychain spam).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_exec.sh"
export CE_TOOL_NAME="minimax-m3"
export GJC_MODEL="${GJC_MODEL:-minimax-code/minimax-m3}"

# Prefer password-free key sources so agents never hammer Keychain.
if [[ -z "${MINIMAX_API_KEY:-}" ]]; then
  if [[ -f "$HOME/.hermes/.env" ]]; then
    # shellcheck disable=SC1091
    MINIMAX_API_KEY="$(grep -E '^MINIMAX_API_KEY=' "$HOME/.hermes/.env" | head -1 | cut -d= -f2- || true)"
    export MINIMAX_API_KEY
  fi
fi
if [[ -z "${MINIMAX_API_KEY:-}" && -f "$HOME/.sinter/config.json" ]]; then
  MINIMAX_API_KEY="$(python3 -c 'import json;from pathlib import Path;d=json.loads(Path.home().joinpath(".sinter/config.json").read_text());print(d.get("providers",{}).get("minimax",{}).get("apiKey") or "")' 2>/dev/null || true)"
  export MINIMAX_API_KEY
fi
# Coding-plan key sometimes required for minimax-code/* model ids
if [[ -z "${CUSTOM_MINIMAX_CODING_PLAN_API_KEY:-}" && -f "$HOME/.hermes/.env" ]]; then
  CUSTOM_MINIMAX_CODING_PLAN_API_KEY="$(grep -E '^CUSTOM_MINIMAX_CODING_PLAN_API_KEY=' "$HOME/.hermes/.env" | head -1 | cut -d= -f2- || true)"
  export CUSTOM_MINIMAX_CODING_PLAN_API_KEY
fi

ce_parse_args "$@"
ce_run_gjc
