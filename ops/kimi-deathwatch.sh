#!/usr/bin/env bash
# Kimi subscription death-watch (Simon, 2026-08-16). The DYING subscription is
# info@kyanitelabs.tech (lane kimi-k3-kyanite, keychain kimi_api_key_kyanite);
# simon@puenteworks.com (OAuth login, survivor) is the control probe. Logs
# pass/fail every 30 minutes so the first hard failures identify the death.
# Log-only; no notifications.
set -uo pipefail
# cron has a minimal PATH and cannot read the login keychain; resolve binaries
# explicitly and fall back to 600-perm key caches.
export PATH="$HOME/.kimi-code/bin:/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin:$PATH"
BASE="$HOME/.local/share/pushing-dispatch"
LOG="${KIMI_DEATHWATCH_LOG:-$BASE/kimi-deathwatch.log}"

probe() {  # $1 = label, $2 = optional api key
    local out
    if [[ -n "${2:-}" ]]; then
        out=$(KIMI_API_KEY="$2" timeout 120 kimi --model kimi-code/k3 --prompt "Reply with exactly: OK" 2>&1 | tail -5)
    else
        out=$(timeout 120 kimi --model kimi-code/k3 --prompt "Reply with exactly: OK" 2>&1 | tail -5)
    fi
    if echo "$out" | grep -q "OK"; then
        printf '%s %s PASS\n' "$(date '+%F %T')" "$1" >>"$LOG"
    else
        printf '%s %s FAIL %s\n' "$(date '+%F %T')" "$1" "$(echo "$out" | tr '\n' ' ' | cut -c1-200)" >>"$LOG"
    fi
}

load_key() {  # $1 = keychain account, $2 = cache file -> echoes secret
    local secret
    secret="$(security find-generic-password -s pushing-dispatch -a "$1" -w 2>/dev/null)"
    if [[ -n "$secret" ]]; then
        printf '%s' "$secret" > "$2"
        chmod 600 "$2"
    elif [[ -s "$2" ]]; then
        secret="$(cat "$2")"
    fi
    printf '%s' "$secret"
}

# Control: survivor account (OAuth credential on this machine).
probe "puenteworks-oauth"

# Dying subscription: info@kyanitelabs.tech API key.
kyanite="$(load_key "kimi_api_key_kyanite" "$BASE/.kimi-kyanite-key-cache")"
if [[ -n "$kyanite" ]]; then
    probe "kyanitelabs-dying" "$kyanite"
else
    printf '%s kyanitelabs-dying SKIP no-key\n' "$(date '+%F %T')" >>"$LOG"
fi
