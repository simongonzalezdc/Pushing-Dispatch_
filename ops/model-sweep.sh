#!/usr/bin/env bash
# Model-drop radar (Simon, 2026-08-16): detect new model releases from every
# provider we already have credentials for (next MiniMax 3.1, Grok 4.7, Kimi
# K3.1, new Ollama Cloud entries, AGY Gemini bumps...). Compares live catalogs
# against the last snapshot; drift is logged with a NEW-MODEL banner for the
# daily digest. Log-only; no notifications.
set -uo pipefail
export PATH="$HOME/.local/bin:$HOME/.bun/bin:$HOME/.kimi-code/bin:/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin:$PATH"
BASE="$HOME/.local/share/pushing-dispatch"
SNAP="$BASE/model-sweep.snapshot"
LOG="$BASE/model-sweep.log"

today="$(mktemp "${TMPDIR:-/tmp}/model-sweep-XXXXXX")"
{
  echo "### ollama-cloud"
  KEY="$(security find-generic-password -s pushing-dispatch -a ollama_api_key -w 2>/dev/null)"
  [[ -z "$KEY" && -s "$BASE/.kimi-key-cache" ]] && KEY="$(head -c1 /dev/null)"  # placeholder, ollama has no cache
  if [[ -n "$KEY" ]]; then
    curl -s -m 20 -H "Authorization: Bearer $KEY" https://ollama.com/v1/models \
      | python3 -c "import json,sys; [print(m['id']) for m in json.load(sys.stdin).get('data',[])]" 2>/dev/null | sort
  fi
  echo "### grok"
  grok models 2>/dev/null | grep -oE 'grok-[0-9.]+[a-z-]*' | sort -u
  echo "### agy"
  agy models 2>/dev/null | awk '{print $1}' | grep -E '^[a-z]' | sort -u
  echo "### gjc"
  gjc models 2>/dev/null | awk 'NR>2 && /^[a-z]/ {print $1}' | sort -u
  echo "### versions"
  echo "kimi $(kimi --version 2>/dev/null | tail -1)"
  echo "zcode $(zcode --version 2>/dev/null | tail -1)"
  echo "dsh $(dsh --version 2>/dev/null | tail -1)"
} > "$today" 2>/dev/null

if [[ ! -s "$SNAP" ]]; then
  cp "$today" "$SNAP"
  printf '%s baseline snapshot created (%s lines)\n' "$(date '+%F %T')" "$(wc -l < "$today" | tr -d ' ')" >>"$LOG"
  rm -f "$today"; exit 0
fi

if diff -q "$SNAP" "$today" >/dev/null 2>&1; then
  printf '%s no provider catalog changes\n' "$(date '+%F %T')" >>"$LOG"
else
  printf '%s *** NEW-MODEL / CATALOG CHANGE DETECTED ***\n' "$(date '+%F %T')" >>"$LOG"
  diff "$SNAP" "$today" | sed 's/^/    /' >>"$LOG"
  printf '%s -> review dispatch_matrix.toml + docs/BENCHMARKS.md, then update lanes\n' "$(date '+%F %T')" >>"$LOG"
  cp "$today" "$SNAP"
fi
rm -f "$today"
