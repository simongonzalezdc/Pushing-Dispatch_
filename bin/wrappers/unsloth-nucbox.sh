#!/usr/bin/env bash
# unsloth-nucbox.sh — Qwen3.8-27B sticky local leaf on :8890 (Ornith rollback on disk).
# Progressive skills: catalog injected (name/desc/path only); full SKILL.md via read tool.
# Pi native --skills discovery is disabled (pulls global package skill bloat past 32k ctx).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_exec.sh"

export CE_TOOL_NAME="unsloth-nucbox"
export PI_LOCAL_PROVIDER="${UNSLOTH_PI_PROVIDER:-unsloth-nucbox}"
export PI_LOCAL_MODEL="${UNSLOTH_MODEL:-unsloth/Qwen3.8-27B-GGUF}"
export PI_LOCAL_AGENT_DIR="${UNSLOTH_PI_AGENT_DIR:-$SCRIPT_DIR/../../ops/unsloth-nucbox/pi-agent}"
export PI_LOCAL_BASE_URL="${UNSLOTH_BASE_URL:-http://100.113.174.74:8890/v1}"
export PI_LOCAL_HEALTH_URL="${PI_LOCAL_BASE_URL%/}/models"
export PI_LOCAL_EXPECT_MODEL="$PI_LOCAL_MODEL"
export PI_LOCAL_TIMEOUT_SECONDS="${PI_LOCAL_TIMEOUT_SECONDS:-600}"
# S+ gates: pre-start gen canary + empty-log early fail + raw diagnostic when proxy dies
export PI_LOCAL_GEN_CANARY="${PI_LOCAL_GEN_CANARY:-1}"
export PI_LOCAL_GEN_CANARY_TIMEOUT="${PI_LOCAL_GEN_CANARY_TIMEOUT:-25}"
export PI_LOCAL_EMPTY_LOG_SECONDS="${PI_LOCAL_EMPTY_LOG_SECONDS:-90}"
export PI_LOCAL_RAW_DIAG_URL="${PI_LOCAL_RAW_DIAG_URL:-http://100.113.174.74:58805/v1}"
# Keep native discovery off; we inject progressive catalog ourselves.
export PI_LOCAL_SKILLS_MODE="${PI_LOCAL_SKILLS_MODE:-off}"
export PI_LOCAL_CONTEXT_FILES="${PI_LOCAL_CONTEXT_FILES:-on}"
export PI_LOCAL_TOOLS="${PI_LOCAL_TOOLS:-read,bash,edit,write,grep,find,ls}"

OPS_DIR="$SCRIPT_DIR/../../ops/unsloth-nucbox"
SYSTEM_FILE="$OPS_DIR/SYSTEM.md"
SKILLS_BLOCK="$OPS_DIR/SKILLS-PROMPT-BLOCK.md"

if [[ -z "${OPENAI_COMPAT_SYSTEM:-}" ]]; then
  OPENAI_COMPAT_SYSTEM=""
  if [[ -f "$SYSTEM_FILE" ]]; then
    OPENAI_COMPAT_SYSTEM="$(cat "$SYSTEM_FILE")"
  fi
  if [[ -f "$SKILLS_BLOCK" ]]; then
    OPENAI_COMPAT_SYSTEM="${OPENAI_COMPAT_SYSTEM}"$'\n\n'"$(cat "$SKILLS_BLOCK")"
  fi
  export OPENAI_COMPAT_SYSTEM
fi
export OPENAI_COMPAT_SYSTEM="${OPENAI_COMPAT_SYSTEM:-You are Ornith local dispatch leaf. End with Status: DONE.}"

ce_parse_args "$@"

# Serialize: exclusive leaf lock for GPU parallel=1 (fail-fast if busy).
# CLI also pre-checks; this covers races and holds the lock for the job lifetime.
_ORNITH_LOCK_RC=0
# Lock against this wrapper shell PID ($$), not the short-lived python helper.
PYTHONPATH="${SCRIPT_DIR}/../..${PYTHONPATH:+:$PYTHONPATH}" python3 - "$CE_WORKER_ID" "$$" <<'PY' || _ORNITH_LOCK_RC=$?
import sys

from dispatch_lib.leaf_serialize import acquire_leaf_lock

worker_id = sys.argv[1]
shell_pid = int(sys.argv[2])
ok, reason = acquire_leaf_lock("unsloth-nucbox", worker_id, pid=shell_pid)
if not ok:
    print(f"Error: {reason}", file=sys.stderr)
    sys.exit(4)
print(f"Ornith leaf lock acquired for {worker_id} pid={shell_pid}", file=sys.stderr)
PY
if [[ "${_ORNITH_LOCK_RC}" -ne 0 ]]; then
  ce_finalize_status "errored" 4 "unsloth-nucbox busy: another Ornith leaf is running (serialize)"
  exit 4
fi
_release_ornith_lock() {
  PYTHONPATH="${SCRIPT_DIR}/../..${PYTHONPATH:+:$PYTHONPATH}" python3 - "$CE_WORKER_ID" <<'PY' || true
import sys
from dispatch_lib.leaf_serialize import release_leaf_lock
release_leaf_lock("unsloth-nucbox", sys.argv[1])
PY
}
trap _release_ornith_lock EXIT

ce_run_pi_local
