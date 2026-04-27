#!/usr/bin/env bash
# auto_poll.sh - Hook to inject auto-polling for active dispatch workers.
#
# Install as a SessionStart and/or UserPromptSubmit hook in Claude Code
# settings.json. When active workers are detected, this hook emits a
# <system-reminder> telling the model to start polling.
#
# Session-scoped: only polls for workers dispatched by THIS session.
# Other concurrent sessions are unaffected.
#
# Usage in settings.json:
#   "hooks": {
#     "SessionStart": [{ "command": "bash /path/to/auto_poll.sh" }],
#     "UserPromptSubmit": [{ "command": "bash /path/to/auto_poll.sh" }]
#   }

set -euo pipefail

DISPATCH_ROOT="${DISPATCH_ROOT:-$HOME/.local/share/pushing-dispatch}"
SESSION_ID="${DISPATCH_SESSION_ID:-${CLAUDE_SESSION_ID:-unknown}}"
MARKER_FILE="$DISPATCH_ROOT/auto_poll_active_${SESSION_ID}"
STALE_MINUTES=30

# Count active workers for this session
count_session_active() {
    local count=0
    local status_dir="$DISPATCH_ROOT/status"
    if [[ ! -d "$status_dir" ]]; then
        echo 0
        return
    fi
    for f in "$status_dir"/*.json; do
        [[ -f "$f" ]] || continue
        # Check if worker belongs to this session and is non-terminal
        local session phase
        session=$(python3 -c "import json; d=json.load(open('$f')); print(d.get('dispatched_by_session_id',''))" 2>/dev/null || echo "")
        phase=$(python3 -c "import json; d=json.load(open('$f')); print(d.get('current_phase','done'))" 2>/dev/null || echo "done")
        if [[ "$session" == "$SESSION_ID" ]]; then
            case "$phase" in
                done|errored|blocked|killed|needs_guidance) ;;
                *) count=$((count + 1)) ;;
            esac
        fi
    done
    echo $count
}

# Check for stale marker
is_marker_stale() {
    if [[ ! -f "$MARKER_FILE" ]]; then
        return 0  # No marker = stale (needs creation)
    fi
    local age
    age=$(( $(date +%s) - $(stat -f %m "$MARKER_FILE" 2>/dev/null || stat -c %Y "$MARKER_FILE" 2>/dev/null || echo 0) ))
    [[ $age -gt $((STALE_MINUTES * 60)) ]]
}

# Main
active=$(count_session_active)

if [[ "$active" -gt 0 ]]; then
    if is_marker_stale; then
        # Create/refresh marker
        mkdir -p "$(dirname "$MARKER_FILE")"
        date +%s > "$MARKER_FILE"

        # Emit system reminder to start polling
        cat <<REMINDER
<system-reminder>
You have $active active dispatch worker(s) from this session.
Start polling with: /loop 90s /dispatch-poll
The loop will auto-terminate when all workers finish.
</system-reminder>
REMINDER
    fi
else
    # No active workers; clean up marker if it exists
    rm -f "$MARKER_FILE"
fi
