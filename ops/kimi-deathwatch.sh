#!/usr/bin/env bash
# Kimi dual-subscription death-watch (Simon, 2026-08-16). One Kimi Code sub
# lapses at end of the billing period; we don't know which. This probe runs a
# trivial prompt on BOTH accounts every 30 minutes and logs pass/fail so the
# first failure identifies the dying subscription. Log-only; no notifications.
set -uo pipefail
LOG="${KIMI_DEATHWATCH_LOG:-$HOME/.local/share/pushing-dispatch/kimi-deathwatch.log}"

probe() {  # $1 = label, stdin none
    local out
    out=$(timeout 120 kimi --model kimi-code/k3 --prompt "Reply with exactly: OK" 2>&1 | tail -5)
    if echo "$out" | grep -q "OK"; then
        printf '%s %s PASS\n' "$(date '+%F %T')" "$1" >>"$LOG"
    else
        printf '%s %s FAIL %s\n' "$(date '+%F %T')" "$1" "$(echo "$out" | tr '\n' ' ' | cut -c1-200)" >>"$LOG"
    fi
}

# Account 1: shared OAuth subscription (default credential).
probe "oauth-sub"

# Account 2: API-key subscription (keychain pushing-dispatch/kimi_api_key).
if secret="$(security find-generic-password -s pushing-dispatch -a kimi_api_key -w 2>/dev/null)" && [[ -n "$secret" ]]; then
    KIMI_API_KEY="$secret" probe "apikey-sub"
else
    printf '%s apikey-sub SKIP no-key\n' "$(date '+%F %T')" >>"$LOG"
fi
