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

# tokflint's stdout is a rendered conversation, not a role-aware receipt. Give
# this one turn a fresh, known session id and finalize only from that session's
# append-only EventLog. A fresh id prevents a prior turn or stale transcript
# from satisfying the completion gate.
CHAMPION_SESSION_ID="$(python3 - <<'PY'
import uuid
print("dispatch-" + uuid.uuid4().hex)
PY
)"
CHAMPION_SESSION_DIR="$HOME/.local/share/liam/sessions"
# Hermetic tests may inject a receipt directory, but only through the explicit
# test hook and only beneath DISPATCH_ROOT. Production ignores this override;
# no global liam/harness setting is changed.
if [[ "${CHAMPION_TEST_HOOK:-0}" == "1" ]]; then
    if [[ -z "${CHAMPION_TEST_SESSION_DIR:-}" ]]; then
        ce_finalize_status "errored" 4 "champion test hook missing receipt directory"
        exit 4
    fi
    if ! python3 - "$CE_DISPATCH_ROOT" "$CHAMPION_TEST_SESSION_DIR" <<'PY'
import os
import sys

root, candidate = map(os.path.realpath, sys.argv[1:3])
try:
    if os.path.commonpath((root, candidate)) != root:
        raise ValueError
except ValueError:
    raise SystemExit(1)
PY
    then
        ce_finalize_status "errored" 4 "champion test receipt directory outside DISPATCH_ROOT"
        exit 4
    fi
    CHAMPION_SESSION_DIR="$CHAMPION_TEST_SESSION_DIR"
fi
CHAMPION_SESSION_RECEIPT="$CHAMPION_SESSION_DIR/${CHAMPION_SESSION_ID}.jsonl"
if [[ -e "$CHAMPION_SESSION_RECEIPT" ]]; then
    ce_finalize_status "errored" 4 "fresh champion session receipt already exists"
    exit 4
fi

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
  --resume "$CHAMPION_SESSION_ID" \
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

# Finalize from the worker role's exact final assistant event, followed by the
# matching turn_done event. This deliberately does not scan stdout: task text,
# tool results, earlier assistant turns, and rendered harness labels are not a
# completion receipt.
CHAMPION_VERDICT=""
CHAMPION_RECEIPT_RC=0
CHAMPION_VERDICT="$(python3 - "$CHAMPION_SESSION_RECEIPT" <<'PY'
import json
import sys

path = sys.argv[1]
try:
    with open(path, encoding="utf-8") as stream:
        events = []
        for line_number, raw in enumerate(stream, 1):
            if not raw.strip():
                continue
            try:
                event = json.loads(raw)
            except (TypeError, ValueError):
                raise ValueError(f"malformed JSONL event at line {line_number}")
            if not isinstance(event, dict):
                raise ValueError(f"malformed event at line {line_number}")
            events.append(event)
except (OSError, ValueError):
    raise SystemExit(4)

# The final assistant event in the known fresh session is the only candidate.
# Requiring a later matching turn_done binds it to a completed harness turn and
# avoids accepting an earlier assistant claim or a tool_result echo.
assistant_indices = [
    i for i, event in enumerate(events)
    if event.get("kind") == "assistant_message"
]
if not assistant_indices:
    raise SystemExit(4)
assistant_index = assistant_indices[-1]
assistant = events[assistant_index]
rid = assistant.get("rid")
tid = assistant.get("tid")
content = assistant.get("content")
if (not isinstance(rid, str) or not rid or not isinstance(tid, str) or not tid
        or not isinstance(content, str)
        or assistant.get("tool_calls")):
    raise SystemExit(4)

matching_done = any(
    i > assistant_index
    and event.get("kind") == "telemetry"
    and event.get("kind_detail") == "turn_done"
    and event.get("rid") == rid
    and event.get("tid") == tid
    for i, event in enumerate(events)
)
if not matching_done:
    raise SystemExit(4)

lines = content.splitlines()
while lines and not lines[-1].strip():
    lines.pop()
if not lines:
    raise SystemExit(4)

terminal = lines[-1].strip()
if terminal not in {
    "Status: DONE",
    "Status: DONE_WITH_CONCERNS",
    "Status: NEEDS_GUIDANCE",
    "Status: BLOCKED",
}:
    raise SystemExit(4)
print(terminal)
PY
)" || CHAMPION_RECEIPT_RC=$?

if [[ $CHAMPION_RECEIPT_RC -ne 0 ]]; then
    ce_finalize_status "errored" 4 "missing/malformed liam receipt or terminal status token"
    exit 4
fi

case "$CHAMPION_VERDICT" in
    "Status: DONE"|"Status: DONE_WITH_CONCERNS")
        echo "Worker $CE_WORKER_ID completed successfully."
        ce_finalize_status "done" 0 ""
        ;;
    "Status: NEEDS_GUIDANCE")
        echo "Worker $CE_WORKER_ID needs guidance." >&2
        ce_finalize_status "needs_guidance" 2 "Worker requested guidance"
        exit 2
        ;;
    "Status: BLOCKED")
        echo "Worker $CE_WORKER_ID is blocked." >&2
        ce_finalize_status "blocked" 3 "Worker reported blocked"
        exit 3
        ;;
    *)
        # The helper is closed over the four exact values above. Keep this
        # guard fail-closed if that contract changes unexpectedly.
        ce_finalize_status "errored" 4 "missing/malformed liam receipt or terminal status token"
        exit 4
        ;;
esac
