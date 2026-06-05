#!/usr/bin/env bash
# check-prereqs.sh - Verify environment prerequisites for pushing-dispatch.
#
# Checks for required and optional tools, reports what's missing.
# Exit 0 if all required prereqs met, exit 1 if any required tool is missing.

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

pass=0
fail=0
warn=0

check_required() {
    local name="$1"
    local cmd="$2"
    local install_hint="$3"

    if command -v "$cmd" &>/dev/null; then
        local version
        version=$($cmd --version 2>&1 | head -1 || echo "unknown")
        echo -e "  ${GREEN}OK${NC}  $name ($version)"
        pass=$((pass + 1))
    else
        echo -e "  ${RED}MISSING${NC}  $name"
        echo "         Install: $install_hint"
        fail=$((fail + 1))
    fi
}

check_optional() {
    local name="$1"
    local cmd="$2"
    local purpose="$3"

    if command -v "$cmd" &>/dev/null; then
        echo -e "  ${GREEN}OK${NC}  $name (optional)"
        pass=$((pass + 1))
    else
        echo -e "  ${YELLOW}SKIP${NC}  $name (optional: $purpose)"
        warn=$((warn + 1))
    fi
}

check_python_version() {
    if command -v python3 &>/dev/null; then
        local ver
        ver=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
        local major minor
        major=$(echo "$ver" | cut -d. -f1)
        minor=$(echo "$ver" | cut -d. -f2)
        if [[ "$major" -ge 3 && "$minor" -ge 11 ]]; then
            echo -e "  ${GREEN}OK${NC}  Python $ver (3.11+ required)"
            pass=$((pass + 1))
        else
            echo -e "  ${RED}FAIL${NC}  Python $ver (3.11+ required)"
            fail=$((fail + 1))
        fi
    else
        echo -e "  ${RED}MISSING${NC}  Python 3.11+"
        echo "         Install: https://python.org/downloads/"
        fail=$((fail + 1))
    fi
}

check_bash_version() {
    local ver
    ver="${BASH_VERSION:-unknown}"
    local major
    major=$(echo "$ver" | cut -d. -f1)
    if [[ "$major" -ge 4 ]]; then
        echo -e "  ${GREEN}OK${NC}  Bash $ver (4+ required)"
        pass=$((pass + 1))
    else
        echo -e "  ${RED}FAIL${NC}  Bash $ver (4+ required)"
        echo "         macOS ships bash 3. Install: brew install bash"
        fail=$((fail + 1))
    fi
}

check_api_key() {
    local name="$1"
    local env_var="$2"

    if [[ -n "${!env_var:-}" ]]; then
        echo -e "  ${GREEN}OK${NC}  $name (via $env_var)"
        pass=$((pass + 1))
    else
        echo -e "  ${YELLOW}SKIP${NC}  $name (set $env_var to enable)"
        warn=$((warn + 1))
    fi
}

check_kimi_oauth() {
    local cred="${KIMI_CREDENTIALS_PATH:-$HOME/.kimi/credentials/kimi-code.json}"

    if ! command -v kimi &>/dev/null && ! command -v kimi-cli &>/dev/null; then
        echo -e "  ${YELLOW}SKIP${NC}  Kimi CLI OAuth (install kimi CLI to enable)"
        warn=$((warn + 1))
        return
    fi

    if python3 - "$cred" <<'PY' >/dev/null 2>&1; then
import json
import sys
import time
from pathlib import Path

path = Path(sys.argv[1])
if not path.exists():
    raise SystemExit(1)
data = json.loads(path.read_text())
if data.get("refresh_token"):
    raise SystemExit(0)
expires_at = data.get("expires_at")
if data.get("access_token") and isinstance(expires_at, (int, float)) and expires_at > time.time():
    raise SystemExit(0)
raise SystemExit(1)
PY
        echo -e "  ${GREEN}OK${NC}  Kimi CLI OAuth (~/.kimi credential store)"
        pass=$((pass + 1))
    else
        echo -e "  ${YELLOW}SKIP${NC}  Kimi CLI OAuth (run: kimi login)"
        warn=$((warn + 1))
    fi
}

echo "pushing-dispatch prerequisite check"
echo "=============================="
echo ""

echo "Required tools:"
check_python_version
check_bash_version
check_required "Git" "git" "https://git-scm.com/downloads"
check_required "Claude Code CLI" "claude" "npm install -g @anthropic-ai/claude-code"

echo ""
echo "Optional tools:"
check_optional "kimi-cli" "kimi" "Kimi native mode"
check_optional "Codex CLI" "codex" "Codex/OpenAI and local OSS dispatch"
check_optional "ollama" "ollama" "Local model dispatch"
check_optional "pass" "pass" "Password store for API keys"

echo ""
echo "CLI/OAuth providers:"
check_kimi_oauth

echo ""
echo "API keys:"
check_api_key "Kimi Coding" "KIMI_API_KEY"
check_api_key "DeepSeek" "DEEPSEEK_API_KEY"
check_api_key "MiniMax" "MINIMAX_API_KEY"
check_api_key "Custom MiniMax Coding Plan" "CUSTOM_MINIMAX_CODING_PLAN_API_KEY"
check_api_key "Inception Labs" "CUSTOM_INCEPTION_API_KEY"
check_api_key "Z.ai" "Z_AI_API_KEY"
check_api_key "Kilo" "KILO_API_KEY"
check_api_key "Gemini" "GEMINI_API_KEY"
check_api_key "Google Gemini fallback" "GOOGLE_API_KEY"
check_api_key "OpenAI API fallback" "OPENAI_API_KEY"
check_api_key "Anthropic API fallback" "ANTHROPIC_API_KEY"

echo ""
echo "=============================="
echo -e "Passed: ${GREEN}$pass${NC}  Failed: ${RED}$fail${NC}  Skipped: ${YELLOW}$warn${NC}"

if [[ $fail -gt 0 ]]; then
    echo ""
    echo "Some required prerequisites are missing. Install them before proceeding."
    exit 1
else
    echo ""
    echo "All required prerequisites met. Run 'bash bin/smoke-test.sh' next."
    exit 0
fi
