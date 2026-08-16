#!/usr/bin/env bash
# zai.sh - GLM 5.3 executor via Z.AI ZCode (`zcode -p`). Canonical path
# per docs/ZCODE.md. The old Claude Code harness (claude-glm52) is retired
# as an executor lane.
#   model: glm-5.3 (ZCode handles its own auth; no key plumbing here)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_exec.sh"

export CE_TOOL_NAME="zai"

ce_parse_args "$@"
ce_run_zcode
