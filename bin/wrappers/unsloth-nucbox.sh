#!/usr/bin/env bash
# unsloth-nucbox.sh — Ornith sticky local leaf on :8890.
# Progressive skills: catalog injected (name/desc/path only); full SKILL.md via read tool.
# Pi native --skills discovery is disabled (pulls global package skill bloat past 32k ctx).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_exec.sh"

export CE_TOOL_NAME="unsloth-nucbox"
export PI_LOCAL_PROVIDER="${UNSLOTH_PI_PROVIDER:-unsloth-nucbox}"
export PI_LOCAL_MODEL="${UNSLOTH_MODEL:-SC117/Ornith-1.0-35B-MTP-APEX-GGUF}"
export PI_LOCAL_AGENT_DIR="${UNSLOTH_PI_AGENT_DIR:-$SCRIPT_DIR/../../ops/unsloth-nucbox/pi-agent}"
export PI_LOCAL_BASE_URL="${UNSLOTH_BASE_URL:-http://100.113.174.74:8890/v1}"
export PI_LOCAL_HEALTH_URL="${PI_LOCAL_BASE_URL%/}/models"
export PI_LOCAL_EXPECT_MODEL="$PI_LOCAL_MODEL"
export PI_LOCAL_TIMEOUT_SECONDS="${PI_LOCAL_TIMEOUT_SECONDS:-600}"
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
ce_run_pi_local
