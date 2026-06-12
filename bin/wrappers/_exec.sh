#!/usr/bin/env bash
# _exec.sh - Shared execution library for pushing-dispatch wrappers.
#
# Every provider wrapper (anthropic.sh, moonshot.sh, deepseek.sh, etc.)
# sources this file and calls ce_run_claude. This library handles:
#   - Argument parsing (--cwd, --task, --task-file, --worker-id, etc.)
#   - Brief assembly (baseline + includes packs + task body)
#   - Prompt template expansion
#   - Claude Code invocation
#   - Stream parsing and exit code mapping
#   - Status file updates
#
# Provider wrappers only set provider-specific env vars and call ce_run_claude.

set -euo pipefail

# --- Paths ---
CE_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CE_REPO_ROOT="$(cd "$CE_SCRIPT_DIR/../.." && pwd)"
CE_DISPATCH_ROOT="${DISPATCH_ROOT:-$HOME/.local/share/pushing-dispatch}"
CE_PACKS_DIR="${DISPATCH_PACKS_DIR:-$CE_REPO_ROOT/dispatch_packs}"
CE_PROMPT_TEMPLATE="$CE_SCRIPT_DIR/executor_prompt.md"

# --- Defaults ---
CE_BARE_MODE="${CE_BARE_MODE:-0}"
CE_TOOL_NAME="${CE_TOOL_NAME:-dispatch-worker}"
CE_MAX_TURNS="${CE_MAX_TURNS:-0}"  # 0 = unlimited
CE_THINKING_TOKENS="${CE_THINKING_TOKENS:-0}"

# --- Argument parsing ---
ce_parse_args() {
    CE_CWD=""
    CE_TASK=""
    CE_TASK_FILE=""
    CE_WORKER_ID=""
    CE_QUESTION_FILE=""
    CE_MODE="task"
    CE_DRY_RUN=0
    CE_READ_ONLY=0
    CE_DISALLOWED_TOOLS=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --cwd) CE_CWD="$2"; shift 2 ;;
            --task) CE_TASK="$2"; shift 2 ;;
            --task-file) CE_TASK_FILE="$2"; shift 2 ;;
            --worker-id) CE_WORKER_ID="$2"; shift 2 ;;
            --question-file) CE_QUESTION_FILE="$2"; shift 2 ;;
            --mode) CE_MODE="$2"; shift 2 ;;
            --dry-run) CE_DRY_RUN=1; shift ;;
            --read-only) CE_READ_ONLY=1; shift ;;
            --max-turns) CE_MAX_TURNS="$2"; shift 2 ;;
            --thinking) CE_THINKING_TOKENS="$2"; shift 2 ;;
            *) echo "Unknown arg: $1" >&2; shift ;;
        esac
    done

    # Default CWD
    if [[ -z "$CE_CWD" ]]; then
        CE_CWD="$(pwd)"
    fi

    # Default worker ID
    if [[ -z "$CE_WORKER_ID" ]]; then
        CE_WORKER_ID="w-$(date +%s | shasum | head -c 4)-adhoc"
    fi

    # Default question file
    if [[ -z "$CE_QUESTION_FILE" ]]; then
        CE_QUESTION_FILE="$CE_DISPATCH_ROOT/questions/${CE_WORKER_ID}.md"
    fi
}

# --- Brief assembly ---
ce_assemble_brief_with_packs() {
    # Reads the task file (or inline task), resolves includes:,
    # prepends baseline, and writes the assembled brief to a temp file.
    #
    # Output: sets CE_ASSEMBLED_BRIEF to the temp file path.

    local baseline="$CE_PACKS_DIR/_baseline.md"
    local registry="$CE_PACKS_DIR/_registry.toml"
    local task_content=""

    if [[ -n "$CE_TASK_FILE" && -f "$CE_TASK_FILE" ]]; then
        task_content="$(cat "$CE_TASK_FILE")"
    elif [[ -n "$CE_TASK" ]]; then
        task_content="$CE_TASK"
    else
        echo "Error: No task provided (--task or --task-file required)" >&2
        return 1
    fi

    # Create temp file for assembled brief
    CE_ASSEMBLED_BRIEF="$(mktemp "${TMPDIR:-/tmp}/dispatch-brief-XXXXXX")"

    # Start with baseline
    if [[ -f "$baseline" ]]; then
        cat "$baseline" >> "$CE_ASSEMBLED_BRIEF"
        echo -e "\n---\n" >> "$CE_ASSEMBLED_BRIEF"
    fi

    # Resolve includes: directives
    # Only match includes: at column 0 (not indented lines in task body)
    local includes_line
    includes_line=$(echo "$task_content" | grep -n '^includes:' | head -1 || true)

    if [[ -n "$includes_line" ]]; then
        local line_num="${includes_line%%:*}"
        local packs_str="${includes_line#*includes:}"
        # Parse pack names (YAML list or inline)
        local packs
        packs=$(echo "$packs_str" | tr -d '[],' | xargs)

        for pack_name in $packs; do
            pack_name=$(echo "$pack_name" | tr -d '"-' | xargs)
            if [[ -z "$pack_name" ]]; then continue; fi

            # Resolve pack path from registry or direct file
            local pack_file="$CE_PACKS_DIR/${pack_name}.md"
            if [[ -f "$pack_file" ]]; then
                echo -e "\n# Pack: $pack_name\n" >> "$CE_ASSEMBLED_BRIEF"
                cat "$pack_file" >> "$CE_ASSEMBLED_BRIEF"
                echo "" >> "$CE_ASSEMBLED_BRIEF"
            else
                echo "Error: Pack not found: $pack_name (looked for $pack_file)" >&2
                rm -f "$CE_ASSEMBLED_BRIEF"
                return 1
            fi
        done

        # Remove the includes: line from task content
        task_content=$(echo "$task_content" | sed "${line_num}d")
    fi

    # Append task content
    echo -e "\n---\n" >> "$CE_ASSEMBLED_BRIEF"
    echo "$task_content" >> "$CE_ASSEMBLED_BRIEF"
}

# --- Prompt assembly ---
ce_assemble_prompt() {
    # Expands the executor_prompt.md template with actual values.
    # Output: sets CE_FINAL_PROMPT to the expanded prompt string.

    if [[ ! -f "$CE_PROMPT_TEMPLATE" ]]; then
        # No template; use the assembled brief directly as the prompt
        CE_FINAL_PROMPT="$(cat "$CE_ASSEMBLED_BRIEF")"
        return
    fi

    local read_only_warning=""
    if [[ "$CE_READ_ONLY" -eq 1 ]]; then
        read_only_warning="WARNING: This is a READ-ONLY task. Do NOT use Write, Edit, or any file-modification tools."
    fi

    local task_content
    task_content="$(cat "$CE_ASSEMBLED_BRIEF")"

    CE_FINAL_PROMPT="$(cat "$CE_PROMPT_TEMPLATE")"
    CE_FINAL_PROMPT="${CE_FINAL_PROMPT//\{\{WORKER_ID\}\}/$CE_WORKER_ID}"
    CE_FINAL_PROMPT="${CE_FINAL_PROMPT//\{\{QUESTION_FILE\}\}/$CE_QUESTION_FILE}"
    CE_FINAL_PROMPT="${CE_FINAL_PROMPT//\{\{READ_ONLY\}\}/$read_only_warning}"
    CE_FINAL_PROMPT="${CE_FINAL_PROMPT//\{\{TASK\}\}/$task_content}"
}

ce_finalize_status() {
    local phase="$1"
    local exit_code="$2"
    local error_summary="${3:-}"

    PYTHONPATH="$CE_REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}" python3 - "$CE_WORKER_ID" "$phase" "$exit_code" "$error_summary" <<'PY'
import sys

from dispatch_lib.status_writer import finalize

worker_id, phase, exit_code, error_summary = sys.argv[1:5]
finalize(worker_id, phase, int(exit_code), error_summary or None)
PY

    # --- Self-healing + outcome recording ---
    # Centralized here so every run path (claude/codex/openai-compat/gemini)
    # gets it. On lane-fault errors (auth/rate_limit/network) the executor is
    # demoted into cooldown so the router reroutes; on success the cooldown is
    # cleared. task/needs_guidance/blocked are NOT lane faults (no demote).
    local log_file="$CE_DISPATCH_ROOT/logs/${CE_WORKER_ID}.log"
    PYTHONPATH="$CE_REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}" python3 - \
        "${CE_EXECUTOR_NAME:-${CE_TOOL_NAME:-unknown}}" "$CE_WORKER_ID" \
        "${CE_TIER:-unknown}" "$phase" "$log_file" <<'PY' 2>/dev/null || true
import sys
from dispatch_lib import lane_health, outcomes
executor, worker_id, tier, phase, log_file = sys.argv[1:6]
if phase == "done":
    lane_health.recover(executor)
    outcomes.record(worker_id, executor, tier, "success", 0.0, 0.0)
elif phase == "errored":
    try:
        text = open(log_file, errors="replace").read()[-4000:]
    except OSError:
        text = ""
    cls = lane_health.classify_failure(text)
    lane_health.demote(executor, cls)          # no-op for task-class
    outcomes.record(worker_id, executor, tier, cls, 0.0, 0.0)
else:
    # needs_guidance / blocked: task-level, not a lane fault.
    outcomes.record(worker_id, executor, tier, "task", 0.0, 0.0)
PY
}

ce_finalize_from_text() {
    local final_text="$1"

    if echo "$final_text" | grep -Eq '^[[:space:]*_`#>-]*Status:[[:space:]]*\*?\*?DONE(_WITH_CONCERNS)?\b'; then
        echo "Worker $CE_WORKER_ID completed successfully."
        ce_finalize_status "done" 0 ""
        return 0
    elif echo "$final_text" | grep -Eq '^[[:space:]*_`#>-]*Status:[[:space:]]*\*?\*?NEEDS_GUIDANCE\b'; then
        echo "Worker $CE_WORKER_ID needs guidance." >&2
        ce_finalize_status "needs_guidance" 2 "Worker requested guidance"
        return 2
    elif echo "$final_text" | grep -Eq '^[[:space:]*_`#>-]*Status:[[:space:]]*\*?\*?BLOCKED\b'; then
        echo "Worker $CE_WORKER_ID is blocked." >&2
        ce_finalize_status "blocked" 3 "Worker reported blocked"
        return 3
    else
        echo "Worker $CE_WORKER_ID completed (no explicit status token)."
        ce_finalize_status "done" 0 ""
        return 0
    fi
}

# --- Main execution ---
ce_run_claude() {
    # Parse args if not already done
    if [[ -z "${CE_CWD:-}" ]]; then
        ce_parse_args "$@"
    fi

    # Assemble brief
    ce_assemble_brief_with_packs

    # Assemble prompt
    ce_assemble_prompt

    # Prepare log file
    local log_dir="$CE_DISPATCH_ROOT/logs"
    mkdir -p "$log_dir"
    local log_file="$log_dir/${CE_WORKER_ID}.log"

    # Write the assembled brief to a temp file for claude -p
    local prompt_file
    prompt_file="$(mktemp "${TMPDIR:-/tmp}/dispatch-prompt-XXXXXX")"
    echo "$CE_FINAL_PROMPT" > "$prompt_file"

    # Build claude command. Claude Code's -p flag expects prompt text, not a
    # filename, so pass the assembled content rather than the temp path.
    local cmd=(
        claude
        -p "$CE_FINAL_PROMPT"
        --output-format stream-json
    )

    # Add provider-specific flags
    if [[ "$CE_BARE_MODE" -eq 1 ]]; then
        cmd+=(--bare)
    fi

    if [[ "$CE_MAX_TURNS" -gt 0 ]]; then
        cmd+=(--max-turns "$CE_MAX_TURNS")
    fi

    # Headless workers cannot answer permission prompts; without an explicit
    # permission mode the harness denies any Bash call that misses the host
    # repo's allowlist, so worker success depended on command-shape luck
    # (kimi-coding "Bash denied" while identical minimax tasks passed,
    # 2026-06-12). Task/breakout workers run in isolated worktrees and need
    # full tool access; read-only consults keep the restrictive default.
    if [[ "$CE_READ_ONLY" -eq 1 ]]; then
        cmd+=(--disallowed-tools "Write,Edit,MultiEdit,NotebookEdit")
    else
        cmd+=(--permission-mode "${CE_PERMISSION_MODE:-bypassPermissions}")
    fi

    # Dry run mode
    if [[ "$CE_DRY_RUN" -eq 1 ]]; then
        echo "DRY RUN - Would execute:"
        echo "  ${cmd[*]}"
        echo ""
        echo "Assembled brief: $CE_ASSEMBLED_BRIEF"
        echo "Prompt file: $prompt_file"
        return 0
    fi

    # Execute
    echo "Dispatching worker $CE_WORKER_ID ($CE_TOOL_NAME)..."

    local exit_code=0
    if [[ -n "$CE_CWD" ]]; then
        (cd "$CE_CWD" && "${cmd[@]}") 2>&1 | tee "$log_file" || exit_code=$?
    else
        "${cmd[@]}" 2>&1 | tee "$log_file" || exit_code=$?
    fi

    # Clean up temp files
    rm -f "$prompt_file" "$CE_ASSEMBLED_BRIEF"

    # Extract final text from stream for status-token scanning.
    local final_text=""
    if [[ -f "$log_file" ]]; then
        final_text="$(tail -200 "$log_file")"
    fi

    # Map worker Status: tokens to documented exit codes.
    # Mapping:
    #   Status: DONE / DONE_WITH_CONCERNS  -> 0
    #   Status: NEEDS_GUIDANCE             -> 2
    #   Status: BLOCKED                    -> 3
    #   claude non-zero (no status token)  -> 4 (distinct from wrapper errors which use 1)
    #   no explicit status + clean exit    -> 0
    if [[ $exit_code -ne 0 ]]; then
        echo "Worker $CE_WORKER_ID: claude exited with code $exit_code." >&2
        ce_finalize_status "errored" 4 "claude exited with code $exit_code"
        return 4
    fi
    ce_finalize_from_text "$final_text"
}

ce_run_codex() {
    if [[ -z "${CE_CWD:-}" ]]; then
        ce_parse_args "$@"
    fi

    ce_assemble_brief_with_packs
    ce_assemble_prompt

    local log_dir="$CE_DISPATCH_ROOT/logs"
    mkdir -p "$log_dir"
    local log_file="$log_dir/${CE_WORKER_ID}.log"

    local prompt_file
    prompt_file="$(mktemp "${TMPDIR:-/tmp}/dispatch-prompt-XXXXXX")"
    echo "$CE_FINAL_PROMPT" > "$prompt_file"

    local cmd=(
        codex
        exec
        --cd "$CE_CWD"
        --sandbox "${CODEX_SANDBOX:-workspace-write}"
    )

    if [[ -n "${CODEX_APPROVAL_POLICY:-}" ]]; then
        cmd+=(-c "approval_policy=\"$CODEX_APPROVAL_POLICY\"")
    fi

    if [[ -n "${CODEX_MODEL:-}" ]]; then
        cmd+=(--model "$CODEX_MODEL")
    fi

    if [[ -n "${CODEX_REASONING_EFFORT:-}" ]]; then
        cmd+=(-c "model_reasoning_effort=\"$CODEX_REASONING_EFFORT\"")
    fi

    if [[ "${CODEX_OSS:-0}" -eq 1 ]]; then
        cmd+=(--oss)
        if [[ -n "${CODEX_LOCAL_PROVIDER:-}" ]]; then
            cmd+=(--local-provider "$CODEX_LOCAL_PROVIDER")
        fi
    fi

    if [[ "$CE_READ_ONLY" -eq 1 ]]; then
        cmd+=(--sandbox read-only)
    fi

    cmd+=(-)

    if [[ "$CE_DRY_RUN" -eq 1 ]]; then
        echo "DRY RUN - Would execute:"
        echo "  ${cmd[*]} < $prompt_file"
        echo ""
        echo "Assembled brief: $CE_ASSEMBLED_BRIEF"
        echo "Prompt file: $prompt_file"
        return 0
    fi

    echo "Dispatching worker $CE_WORKER_ID (codex)..."

    local exit_code=0
    "${cmd[@]}" < "$prompt_file" 2>&1 | tee "$log_file" || exit_code=$?

    rm -f "$prompt_file" "$CE_ASSEMBLED_BRIEF"

    local final_text=""
    if [[ -f "$log_file" ]]; then
        final_text="$(tail -200 "$log_file")"
    fi

    if [[ $exit_code -ne 0 ]]; then
        echo "Worker $CE_WORKER_ID: codex exited with code $exit_code." >&2
        ce_finalize_status "errored" 4 "codex exited with code $exit_code"
        return 4
    fi

    ce_finalize_from_text "$final_text"
}

ce_run_openai_compatible() {
    if [[ -z "${CE_CWD:-}" ]]; then
        ce_parse_args "$@"
    fi

    ce_assemble_brief_with_packs
    ce_assemble_prompt

    local log_dir="$CE_DISPATCH_ROOT/logs"
    mkdir -p "$log_dir"
    local log_file="$log_dir/${CE_WORKER_ID}.log"

    if [[ "$CE_DRY_RUN" -eq 1 ]]; then
        echo "DRY RUN - Would POST OpenAI-compatible request:"
        echo "  base_url=${OPENAI_COMPAT_BASE_URL:-}"
        echo "  path=${OPENAI_COMPAT_PATH:-/chat/completions}"
        echo "  model=${OPENAI_COMPAT_MODEL:-}"
        echo "  reasoning_effort=${OPENAI_COMPAT_REASONING_EFFORT:-}"
        echo "  max_tokens=${OPENAI_COMPAT_MAX_TOKENS:-}"
        echo ""
        echo "Assembled brief: $CE_ASSEMBLED_BRIEF"
        return 0
    fi

    echo "Dispatching worker $CE_WORKER_ID (${CE_TOOL_NAME})..."

    local exit_code=0
    OPENAI_COMPAT_PROMPT="$CE_FINAL_PROMPT" python3 - <<'PY' 2>&1 | tee "$log_file" || exit_code=$?
import json
import os
import sys
import urllib.error
import urllib.request

base_url = os.environ["OPENAI_COMPAT_BASE_URL"].rstrip("/")
path = os.environ.get("OPENAI_COMPAT_PATH", "/chat/completions")
model = os.environ["OPENAI_COMPAT_MODEL"]
token = os.environ["OPENAI_COMPAT_API_KEY"]
prompt = os.environ["OPENAI_COMPAT_PROMPT"]

body = {
    "model": model,
    "messages": [{"role": "user", "content": prompt}],
    "stream": False,
}

max_tokens = os.environ.get("OPENAI_COMPAT_MAX_TOKENS")
if max_tokens:
    body["max_tokens"] = int(max_tokens)

reasoning_effort = os.environ.get("OPENAI_COMPAT_REASONING_EFFORT")
if reasoning_effort:
    body["reasoning"] = {"effort": reasoning_effort}

if os.environ.get("OPENAI_COMPAT_INCLUDE_REASONING") == "1":
    body["include_reasoning"] = True

temperature = os.environ.get("OPENAI_COMPAT_TEMPERATURE")
if temperature:
    body["temperature"] = float(temperature)

think = os.environ.get("OPENAI_COMPAT_THINK")
if think:
    body["think"] = think.strip().lower() in {"1", "true", "yes", "on"}

req = urllib.request.Request(
    base_url + path,
    data=json.dumps(body).encode("utf-8"),
    headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    },
    method="POST",
)

try:
    with urllib.request.urlopen(req, timeout=int(os.environ.get("OPENAI_COMPAT_TIMEOUT", "120"))) as resp:
        data = json.loads(resp.read().decode("utf-8"))
except urllib.error.HTTPError as exc:
    detail = exc.read().decode("utf-8", errors="replace")
    print(f"HTTP {exc.code}: {detail}", file=sys.stderr)
    raise SystemExit(1)

print(json.dumps({"type": "system", "model": model, "provider": os.environ.get("CE_TOOL_NAME", "openai-compatible")}))

text = ""
choices = data.get("choices") or []
if choices:
    msg = choices[0].get("message") or {}
    content = msg.get("content")
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        text = "\n".join(part.get("text", "") for part in content if isinstance(part, dict))

if not text:
    text = json.dumps(data)

print(text)
PY

    rm -f "$CE_ASSEMBLED_BRIEF"

    local final_text=""
    if [[ -f "$log_file" ]]; then
        final_text="$(tail -200 "$log_file")"
    fi

    if [[ $exit_code -ne 0 ]]; then
        echo "Worker $CE_WORKER_ID: ${CE_TOOL_NAME} exited with code $exit_code." >&2
        ce_finalize_status "errored" 4 "${CE_TOOL_NAME} exited with code $exit_code"
        return 4
    fi

    ce_finalize_from_text "$final_text"
}

ce_run_gemini() {
    if [[ -z "${CE_CWD:-}" ]]; then
        ce_parse_args "$@"
    fi

    ce_assemble_brief_with_packs
    ce_assemble_prompt

    local log_dir="$CE_DISPATCH_ROOT/logs"
    mkdir -p "$log_dir"
    local log_file="$log_dir/${CE_WORKER_ID}.log"

    if [[ "$CE_DRY_RUN" -eq 1 ]]; then
        echo "DRY RUN - Would POST Gemini generateContent request:"
        echo "  model=${GEMINI_MODEL:-}"
        echo "  thinking_budget=${GEMINI_THINKING_BUDGET:-}"
        echo "  max_tokens=${GEMINI_MAX_TOKENS:-}"
        echo ""
        echo "Assembled brief: $CE_ASSEMBLED_BRIEF"
        return 0
    fi

    echo "Dispatching worker $CE_WORKER_ID (${CE_TOOL_NAME})..."

    local exit_code=0
    GEMINI_PROMPT="$CE_FINAL_PROMPT" python3 - <<'PY' 2>&1 | tee "$log_file" || exit_code=$?
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

model = os.environ["GEMINI_MODEL"]
key = os.environ["GEMINI_API_KEY_EFFECTIVE"]
prompt = os.environ["GEMINI_PROMPT"]

body = {
    "contents": [{"role": "user", "parts": [{"text": prompt}]}],
    "generationConfig": {},
}

max_tokens = os.environ.get("GEMINI_MAX_TOKENS")
if max_tokens:
    body["generationConfig"]["maxOutputTokens"] = int(max_tokens)

temperature = os.environ.get("GEMINI_TEMPERATURE")
if temperature:
    body["generationConfig"]["temperature"] = float(temperature)

thinking_budget = os.environ.get("GEMINI_THINKING_BUDGET")
if thinking_budget:
    body["generationConfig"]["thinkingConfig"] = {"thinkingBudget": int(thinking_budget)}

url = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    + urllib.parse.quote(model, safe="")
    + ":generateContent?key="
    + urllib.parse.quote(key, safe="")
)

req = urllib.request.Request(
    url,
    data=json.dumps(body).encode("utf-8"),
    headers={"Content-Type": "application/json", "Accept": "application/json"},
    method="POST",
)

try:
    with urllib.request.urlopen(req, timeout=int(os.environ.get("GEMINI_TIMEOUT", "120"))) as resp:
        data = json.loads(resp.read().decode("utf-8"))
except urllib.error.HTTPError as exc:
    detail = exc.read().decode("utf-8", errors="replace")
    print(f"HTTP {exc.code}: {detail}", file=sys.stderr)
    raise SystemExit(1)

print(json.dumps({"type": "system", "model": model, "provider": "gemini"}))

texts = []
for candidate in data.get("candidates", []):
    content = candidate.get("content") or {}
    for part in content.get("parts", []):
        if isinstance(part, dict) and part.get("text"):
            texts.append(part["text"])

print("\n".join(texts) if texts else json.dumps(data))
PY

    rm -f "$CE_ASSEMBLED_BRIEF"

    local final_text=""
    if [[ -f "$log_file" ]]; then
        final_text="$(tail -200 "$log_file")"
    fi

    if [[ $exit_code -ne 0 ]]; then
        echo "Worker $CE_WORKER_ID: gemini exited with code $exit_code." >&2
        ce_finalize_status "errored" 4 "gemini exited with code $exit_code"
        return 4
    fi

    ce_finalize_from_text "$final_text"
}

# --- API key loading helpers ---

# Generic keychain loader (macOS). Falls back to env var.
ce_sanitize_anthropic_env() {
    # Anthropic lanes must hit the real API. The dispatching session often
    # carries ANTHROPIC_* overrides (proxy base URLs, foreign auth tokens, GLM
    # model aliases) that 401 or silently misroute OAuth creds (2026-06-12).
    # Headless `claude -p` on such rigs also needs a long-lived token from
    # `claude setup-token` — keychain OAuth alone does not serve it (same
    # recipe as liminal's fable-watchman).
    unset ANTHROPIC_BASE_URL ANTHROPIC_AUTH_TOKEN ANTHROPIC_API_KEY \
          ANTHROPIC_DEFAULT_HAIKU_MODEL ANTHROPIC_DEFAULT_OPUS_MODEL ANTHROPIC_DEFAULT_SONNET_MODEL
    local _tok
    for _tok in "$HOME/.claude/dispatch-token" "$HOME/.claude/watchman-token"; do
        if [[ -z "${CLAUDE_CODE_OAUTH_TOKEN:-}" && -f "$_tok" ]]; then
            export CLAUDE_CODE_OAUTH_TOKEN="$(cat "$_tok")"
        fi
    done
}

ce_load_api_key() {
    local service="$1"
    local account="$2"
    local env_var="$3"

    # Try env var first
    local val="${!env_var:-}"
    if [[ -n "$val" ]]; then
        echo "$val"
        return
    fi

    # Try macOS Keychain
    if command -v security &>/dev/null; then
        val=$(security find-generic-password -s "$service" -a "$account" -w 2>/dev/null || true)
        if [[ -n "$val" ]]; then
            echo "$val"
            return
        fi
    fi

    # Try pass (password store)
    if command -v pass &>/dev/null; then
        val=$(pass show "$service/$account" 2>/dev/null | head -1 || true)
        if [[ -n "$val" ]]; then
            echo "$val"
            return
        fi
    fi

    # Try Codex config. Some Manifest-era keys are already registered for
    # Codex MCP servers or shell environment policy rather than exported in the
    # current shell.
    if [[ -f "$HOME/.codex/config.toml" ]]; then
        val=$(python3 - "$HOME/.codex/config.toml" "$env_var" <<'PY' 2>/dev/null || true
import sys
import tomllib

config_path, env_var = sys.argv[1:3]
with open(config_path, "rb") as f:
    cfg = tomllib.load(f)

shell_set = cfg.get("shell_environment_policy", {}).get("set", {})
val = shell_set.get(env_var)
if val:
    print(val)
    raise SystemExit(0)

for server in cfg.get("mcp_servers", {}).values():
    env = server.get("env", {})
    val = env.get(env_var)
    if val:
        print(val)
        raise SystemExit(0)
PY
)
        if [[ -n "$val" ]]; then
            echo "$val"
            return
        fi
    fi

    echo "Error: API key not found for $service/$account." >&2
    echo "Set $env_var env var, or store in macOS Keychain (service=$service, account=$account)." >&2
    return 1
}
