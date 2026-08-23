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

# Write the task to a file (handles quoting)
printf '%s' "$CE_TASK" > "$TASK_FILE"

# Execute via tokflint with --yolo (no confirmation gates)
timeout "${CHAMPION_TIMEOUT:-900}" python3 "$TOKFLINT_DIR/tokflint.py" run \
  --task "$(cat "$TASK_FILE")" \
  --yolo \
  > /tmp/dispatch-result-$$.log 2>&1
EXIT_CODE=$?

rm -f "$TASK_FILE"

if [[ $EXIT_CODE -ne 0 ]]; then
    echo "Error: tokflint exited $EXIT_CODE" >&2
    tail -5 /tmp/dispatch-result-$$.log >&2
    rm -f /tmp/dispatch-result-$$.log
    exit $EXIT_CODE
fi

# Output the result (tokflint prints the conversation)
cat /tmp/dispatch-result-$$.log
rm -f /tmp/dispatch-result-$$.log

ce_finalize_from_text "Status: DONE"
