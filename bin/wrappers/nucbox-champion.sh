#!/usr/bin/env bash
# nucbox-champion.sh — the ONE local lane (CEO policy: champion-only on the NUC).
# Serves the resident Qwen3.8-27B UD-Q4_XL llama-server (qwen27.service) through
# the qwen27-forward TCP forwarder (tailscale :46380 -> 127.0.0.1:46377 on-box).
# Champion config: 262144 ctx, q4_0 KV, MTP+ngram spec — DO NOT stack experiments
# against this endpoint (GPU-window laws; it is the resident, not a bench box).
# Replaces the retired unsloth-nucbox sticky-leaf lane (S-069-adjacent retirement).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_exec.sh"

export CE_TOOL_NAME="nucbox-champion"
export PI_LOCAL_PROVIDER="${CHAMPION_PI_PROVIDER:-nucbox-champion}"
export PI_LOCAL_MODEL="${CHAMPION_MODEL:-Qwen3.8-27B}"
export PI_LOCAL_AGENT_DIR="${CHAMPION_PI_AGENT_DIR:-$SCRIPT_DIR/../../ops/nucbox-champion/pi-agent}"
export PI_LOCAL_BASE_URL="${CHAMPION_BASE_URL:-http://100.113.174.74:46380/v1}"
export PI_LOCAL_HEALTH_URL="${PI_LOCAL_BASE_URL%/}/models"
export PI_LOCAL_EXPECT_MODEL="$PI_LOCAL_MODEL"
export PI_LOCAL_TIMEOUT_SECONDS="${CHAMPION_TIMEOUT_SECONDS:-900}"
# S+ gates: pre-start gen canary + empty-log early fail (resident is remote —
# the forwarder can be up while the champion is mid-restart)
export PI_LOCAL_GEN_CANARY="${PI_LOCAL_GEN_CANARY:-1}"
export PI_LOCAL_GEN_CANARY_TIMEOUT="${PI_LOCAL_GEN_CANARY_TIMEOUT:-30}"
export PI_LOCAL_EMPTY_LOG_SECONDS="${PI_LOCAL_EMPTY_LOG_SECONDS:-90}"
export PI_LOCAL_SKILLS_MODE="${PI_LOCAL_SKILLS_MODE:-off}"
export PI_LOCAL_CONTEXT_FILES="${PI_LOCAL_CONTEXT_FILES:-on}"
export PI_LOCAL_TOOLS="${PI_LOCAL_TOOLS:-read,bash,edit,write,grep,find,ls}"

OPS_DIR="$SCRIPT_DIR/../../ops/nucbox-champion"
SYSTEM_FILE="$OPS_DIR/SYSTEM.md"
mkdir -p "$OPS_DIR/pi-agent"
cat > "$SYSTEM_FILE" <<'SYS'
# nucbox-champion — resident Qwen3.8-27B (UD-Q4_XL, 262k ctx, q4_0 KV, MTP+ngram spec)

You are served by the KyaniteLabs resident champion on the NUCBox. Constraints:
- This is the PRODUCTION resident: no benchmark traffic, no experiment stacking,
  no restarts (GPU-window laws apply; experiments run on separate windows).
- 262144-token context; long-context work is the lane's purpose (maintaining, not
  loading — prefill economics: don't stuff context you won't use).
- Effort/reasoning-budget is server-side (2048 default); do not attempt to
  re-tune the champion from this lane.
SYS

# Serialize: the resident runs --parallel 1 — one leaf at a time, explicit lock.
_ORNITH_LOCK_RC=0
PYTHONPATH="${SCRIPT_DIR}/../..${PYTHONPATH:+:$PYTHONPATH}" python3 - "$CE_WORKER_ID" "$$" <<'PY' || _ORNITH_LOCK_RC=$?
import sys
from dispatch_lib.leaf_serialize import acquire_leaf_lock
shell_pid = sys.argv[2] if len(sys.argv) > 2 else None
ok, reason = acquire_leaf_lock("nucbox-champion", sys.argv[1], pid=shell_pid)
if not ok:
    print(f"Error: {reason}", file=sys.stderr)
    sys.exit(4)
print(f"Champion leaf lock acquired for {sys.argv[1]}", file=sys.stderr)
PY
if [[ "${_ORNITH_LOCK_RC}" -ne 0 ]]; then
  ce_finalize_status "errored" 4 "nucbox-champion busy: another champion leaf is running (serialize)"
  exit 4
fi
_release_champion_lock() {
  PYTHONPATH="${SCRIPT_DIR}/../..${PYTHONPATH:+:$PYTHONPATH}" python3 - "$CE_WORKER_ID" <<'PY' || true
import sys
from dispatch_lib.leaf_serialize import release_leaf_lock
release_leaf_lock("nucbox-champion", sys.argv[1])
PY
}
trap _release_champion_lock EXIT

ce_run_pi_local
