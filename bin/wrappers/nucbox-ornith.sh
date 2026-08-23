#!/usr/bin/env bash
# nucbox-ornith.sh — Ornith-1.5-35B-A3B APEX on :46399 (co-resident with champion).
# Zero-cost local speed lane: ~55 tok/s decode, 2x champion. Thinking-on default.
# Not for: agent tool loops (champion's cache advantage), quick terse answers.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_exec.sh"
export CE_TOOL_NAME="nucbox-ornith"
export PI_LOCAL_PROVIDER="nucbox-ornith"
export PI_LOCAL_MODEL="Ornith-1.5-35B"
export PI_LOCAL_AGENT_DIR="$SCRIPT_DIR/../../ops/nucbox-ornith/pi-agent"
export PI_LOCAL_BASE_URL="${ORINTH_BASE_URL:-http://100.113.174.74:46399/v1}"
export PI_LOCAL_HEALTH_URL="${ORNITH_HEALTH_URL:-http://100.113.174.74:46399/v1/models}"
export PI_LOCAL_EXPECT_MODEL="Ornith-1.5-35B"
export PI_LOCAL_TIMEOUT_SECONDS="${ORNITH_TIMEOUT_SECONDS:-900}"
export PI_LOCAL_GEN_CANARY=1
export PI_LOCAL_GEN_CANARY_TIMEOUT=30
export PI_LOCAL_EMPTY_LOG_SECONDS=90
export PI_LOCAL_SKILLS_MODE="off"
export PI_LOCAL_CONTEXT_FILES="on"
export PI_LOCAL_TOOLS="read,bash,edit,write,grep,find,ls"
exec "$SCRIPT_DIR/_pi_local.sh" "$@"
