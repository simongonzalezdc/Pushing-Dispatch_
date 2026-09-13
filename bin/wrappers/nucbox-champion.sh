#!/usr/bin/env bash
# nucbox-champion.sh — Qwen3.8-27B via tokflint (FULL AGENT: bash, read, write,
# edit, grep, find, code tools). Zero-cost local lane, certified, 262k ctx.
# Best for: agent tool loops, code tasks, file operations. ~26 tok/s prose.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_exec.sh"

export CE_TOOL_NAME="nucbox-champion"

# Steer tokflint to the champion (via socat forwarder on the NUC)
# NOTE: NO /v1 suffix — tokflint's adapter appends /v1/chat/completions itself
export LIAM_API="${CHAMPION_LIAM_API:-http://100.113.174.74:46380}"
export LIAM_MODEL="${CHAMPION_MODEL:-Qwen3.8-27B}"

# tokflint home + task execution
TOKFLINT_DIR="${TOKFLINT_DIR:-$HOME/workspaces/liam-core}"
TASK_FILE="/tmp/dispatch-task-$$.txt"

ce_parse_args "$@"

# Retained at the path the status file's log_path already advertises; stdout
# alone is not evidence (dispatch task start attaches it to DEVNULL).
LOG_FILE="$CE_DISPATCH_ROOT/logs/${CE_WORKER_ID}.log"

# Write the task to a file (handles quoting). Append the terminal-status
# contract so the finalize gate can require the worker's own token
# (same doctrine as ce_run_zcode; without it this lane could never
# honestly report anything but the wrapper's hardcoded string).
printf '%s\n\nOutput contract: your final line must be exactly "Status: DONE", "Status: DONE_WITH_CONCERNS", "Status: NEEDS_GUIDANCE", or "Status: BLOCKED", in English.\n' "$CE_TASK" > "$TASK_FILE"

# Execute via tokflint with --yolo (no confirmation gates), inside the
# dispatched --cwd so the harness boots in the assigned checkout. Ignoring
# CE_CWD anchored w-8027-task to the dispatcher's live checkout and it read
# the old org-bus tree instead of the assigned worktree.
EXIT_CODE=0
( cd "$CE_CWD" && timeout "${CHAMPION_TIMEOUT:-900}" python3 "$TOKFLINT_DIR/tokflint.py" run \
  --task "$(cat "$TASK_FILE")" \
  --yolo ) > "$LOG_FILE" 2>&1 || EXIT_CODE=$?

rm -f "$TASK_FILE"

if [[ $EXIT_CODE -ne 0 ]]; then
    echo "Error: tokflint exited $EXIT_CODE" >&2
    tail -5 "$LOG_FILE" >&2
    ce_finalize_status "errored" 4 "tokflint exited $EXIT_CODE"
    exit $EXIT_CODE
fi

# Output the result (tokflint prints the conversation); $LOG_FILE is retained.
cat "$LOG_FILE"

# Fail closed on the worker's own terminal token: a tokflint exit 0 only means
# the turn ended (w-8027-task: turn_done + wrong checkout still said DONE).
ce_finalize_from_text "$(tail -200 "$LOG_FILE")"
