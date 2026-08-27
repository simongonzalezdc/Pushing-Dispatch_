#!/usr/bin/env bash
# zai-flash.sh - GLM-5.3-Flash executor via Z.AI ZCode under an isolated HOME.
# Same Coding Plan as zai.sh (zero marginal cost, same fair-use/1313 burst law);
# the flash-home config pins model zai/glm-5.3-flash. Released 2026-08-26.
# Door recipe: ~/.agents/docs/ZCODE-GLM.md 2026-08-26 addendum.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_exec.sh"

export CE_TOOL_NAME="zai-glm-flash"

ce_parse_args "$@"

FLASH_HOME="${ZCODE_FLASH_HOME:-$HOME/.zcode/flash-home}"
FLASH_CONFIG="$FLASH_HOME/.zcode/cli/config.json"
PINNED_MODEL="zai/glm-5.3-flash"

# Fail closed: config drift must never silently run on glm-5.3 (silent
# fallback is the failure mode the control test caught on 2026-08-26).
if [[ -f "$FLASH_CONFIG" ]]; then
    actual="$(python3 -c "import json;print(json.load(open('$FLASH_CONFIG'))['model']['main'])" 2>/dev/null || echo MISSING)"
    if [[ "$actual" != "$PINNED_MODEL" ]]; then
        echo "zai-flash: flash-home model is '$actual' (expected $PINNED_MODEL) — refusing." >&2
        echo "Fix: copy provider block from ~/.zcode/cli/config.json into $FLASH_CONFIG with model.main = $PINNED_MODEL (key rotates with the main config)." >&2
        exit 3
    fi
elif [[ "$CE_DRY_RUN" -ne 1 ]]; then
    echo "zai-flash: $FLASH_CONFIG missing — refusing (see ~/.agents/docs/ZCODE-GLM.md)." >&2
    exit 3
fi

export ZCODE_HOME="$FLASH_HOME"

ce_run_zcode
