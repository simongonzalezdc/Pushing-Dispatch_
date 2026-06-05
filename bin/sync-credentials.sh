#!/usr/bin/env bash
# sync-credentials.sh - Consolidate provider API keys into the macOS Keychain
# service "pushing-dispatch" so non-interactive dispatch subprocesses can reach
# them. Idempotent. Never prints secret values.
#
# Sources harvested (in priority order, first hit wins):
#   1. existing pushing-dispatch Keychain entry (kept as-is)
#   2. interactive zsh exports (your ~/.zshrc)
#   3. ~/.config/goose/.env
#   4. dopamine-depot Keychain entries (service "dopamine-depot:<name>")
#   5. local Manifest/Kilo auth stores for custom provider keys
#   6. Factory .env.local for NUC local inference keys
set -euo pipefail

SERVICE="pushing-dispatch"
GOOSE_ENV="$HOME/.config/goose/.env"

# account_name | env_var | goose_env_key | dopamine_service(optional)
MAP=(
  "kimi_api_key|KIMI_API_KEY||"
  "deepseek_api_key|DEEPSEEK_API_KEY||"
  "minimax_api_key|MINIMAX_API_KEY|MINIMAX_API_KEY|dopamine-depot:minimax"
  "custom_minimax_coding_plan_api_key|CUSTOM_MINIMAX_CODING_PLAN_API_KEY||"
  "custom_inception_api_key|CUSTOM_INCEPTION_API_KEY||"
  "z_ai_api_key|Z_AI_API_KEY||"
  "kilo_api_key|KILO_API_KEY||"
  "gemini_api_key|GEMINI_API_KEY||dopamine-depot:gemini"
  "local_api_key|LOCAL_API_KEY||"
  "pipeline_local_llm_api_key|PIPELINE_LOCAL_LLM_API_KEY||"
)

# Harvest currently-exported keys from an interactive zsh (sources ~/.zshrc).
declare -A ZSH_KEYS
if command -v zsh >/dev/null 2>&1; then
  while IFS='=' read -r k v; do
    [[ -n "$k" ]] && ZSH_KEYS["$k"]="$v"
  done < <(zsh -ic 'for v in KIMI_API_KEY DEEPSEEK_API_KEY MINIMAX_API_KEY CUSTOM_MINIMAX_CODING_PLAN_API_KEY CUSTOM_INCEPTION_API_KEY Z_AI_API_KEY KILO_API_KEY GEMINI_API_KEY GOOGLE_API_KEY LOCAL_API_KEY PIPELINE_LOCAL_LLM_API_KEY; do [[ -n "${(P)v:-}" ]] && print "$v=${(P)v}"; done' 2>/dev/null || true)
fi

get_from_goose() {
  [[ -f "$GOOSE_ENV" ]] || return 0
  grep -E "^$1=" "$GOOSE_ENV" 2>/dev/null | head -1 | cut -d= -f2- || true
}

get_from_dopamine() {
  # arg is the full Keychain service name, account is always "dopamine-depot"
  security find-generic-password -s "$1" -a "dopamine-depot" -w 2>/dev/null || true
}

get_from_codex_config() {
  # Mirror ce_load_api_key: read shell_environment_policy.set or mcp_servers env
  # from ~/.codex/config.toml. arg is the env var name.
  local cfg="$HOME/.codex/config.toml"
  [[ -f "$cfg" ]] || return 0
  python3 - "$cfg" "$1" <<'PY' 2>/dev/null || true
import sys, tomllib
cfg_path, env_var = sys.argv[1:3]
with open(cfg_path, "rb") as f:
    cfg = tomllib.load(f)
val = cfg.get("shell_environment_policy", {}).get("set", {}).get(env_var)
if not val:
    for server in cfg.get("mcp_servers", {}).values():
        v = server.get("env", {}).get(env_var)
        if v:
            val = v
            break
if val:
    print(val)
PY
}

get_from_kilo_auth() {
  # Kilo/Manifest stores custom provider keys in JSON auth files. Never print
  # values; only return the requested secret to the caller for Keychain storage.
  local account="$1"
  python3 - "$account" "$HOME/.local/share/kilo/auth.json" "$HOME/manifest-runtime/secrets/kilo-auth.json" <<'PY' 2>/dev/null || true
import json
import sys
from pathlib import Path

account = sys.argv[1]
paths = [Path(p) for p in sys.argv[2:]]
for path in paths:
    if not path.exists():
        continue
    try:
        data = json.loads(path.read_text())
    except Exception:
        continue
    value = None
    if account == "custom_minimax_coding_plan_api_key":
        row = data.get("minimax-coding-plan")
        if isinstance(row, dict):
            value = row.get("key")
    if value:
        print(value)
        raise SystemExit(0)
PY
}

get_from_factory_env() {
  local envname="$1"
  python3 - "$envname" \
    "$HOME/workspaces/personal/the-factory/.env.local" \
    "$HOME/workspaces/personal/the-factory/.env" <<'PY' 2>/dev/null || true
import re
import sys
from pathlib import Path

envname = sys.argv[1]
pattern = re.compile(rf"(?m)^\s*(?:export\s+)?{re.escape(envname)}\s*=\s*(.+?)\s*$")
for raw in sys.argv[2:]:
    path = Path(raw)
    if not path.exists():
        continue
    match = pattern.search(path.read_text(errors="replace"))
    if match:
        print(match.group(1).strip().strip('"').strip("'"))
        raise SystemExit(0)
PY
}

echo "Credential sync into Keychain service '$SERVICE'"
echo "================================================"
for row in "${MAP[@]}"; do
  IFS='|' read -r acct envname goosekey dopamine <<< "$row"
  if security find-generic-password -s "$SERVICE" -a "$acct" >/dev/null 2>&1; then
    echo "  keep   $acct (already in $SERVICE)"; continue
  fi
  val=""
  [[ -z "$val" && -n "${ZSH_KEYS[$envname]:-}" ]] && val="${ZSH_KEYS[$envname]}"
  [[ -z "$val" && -n "$goosekey" ]] && val="$(get_from_goose "$goosekey")"
  [[ -z "$val" && -n "$dopamine" ]] && val="$(get_from_dopamine "$dopamine")"
  [[ -z "$val" ]] && val="$(get_from_kilo_auth "$acct")"
  [[ -z "$val" ]] && val="$(get_from_factory_env "$envname")"
  [[ -z "$val" ]] && val="$(get_from_codex_config "$envname")"
  if [[ -n "$val" ]]; then
    security add-generic-password -s "$SERVICE" -a "$acct" -w "$val" -U >/dev/null
    echo "  SET    $acct"
  else
    echo "  miss   $acct (no source found)"
  fi
done
echo "------------------------------------------------"
echo "CLI-auth providers (no key needed):"
if [[ -f "$HOME/.codex/auth.json" ]]; then echo "  ok     openai (codex auth.json)"; else echo "  MISS   openai (run: codex login)"; fi
if [[ -f "$HOME/.kimi/credentials/kimi-code.json" ]]; then echo "  ok     kimi-cli (~/.kimi OAuth credentials)"; else echo "  MISS   kimi-cli (run: kimi login)"; fi
echo "  ok     anthropic (claude code login)"
echo
echo "Done. Verify reachability with: python3 cli.py doctor"
