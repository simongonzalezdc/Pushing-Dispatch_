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

    # Wave-2 FM-01/02: heartbeat so telemetry-blind harnesses (dsh, luna)
    # show liveness. Reaper treats stale-but-young as alive.
    (
        while :; do
            printf '{"ts":%s,"pid":%s,"log_bytes":%s}\n' "$(date +%s)" "$$"                 "$(wc -c < "$CE_DISPATCH_ROOT/logs/${CE_WORKER_ID}.log" 2>/dev/null || echo 0)"                 > "$CE_DISPATCH_ROOT/status/${CE_WORKER_ID}.heartbeat" 2>/dev/null || true
            sleep 60
        done
    ) &
    CE_HEARTBEAT_PID=$!
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

    # Wave-2: stop the heartbeat; every terminal path lands here.
    [[ -n "${CE_HEARTBEAT_PID:-}" ]] && kill "$CE_HEARTBEAT_PID" 2>/dev/null || true
    rm -f "$CE_DISPATCH_ROOT/status/${CE_WORKER_ID}.heartbeat" 2>/dev/null || true

    PYTHONPATH="$CE_REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}" python3 - "$CE_WORKER_ID" "$phase" "$exit_code" "$error_summary" <<'PY'
import sys

from dispatch_lib.status_writer import finalize

worker_id, phase, exit_code, error_summary = sys.argv[1:5]
finalize(worker_id, phase, int(exit_code), error_summary or None)
PY

    # DQ-1 fix: side-door visibility. Adhoc invocations (direct wrapper runs,
    # no pipeline worker-id) never had budget rows -- the stall was coverage,
    # not breakage. Cost/tokens unknown at this layer: volume row, source-tagged.
    if [[ "$CE_WORKER_ID" == *-adhoc ]]; then
        PYTHONPATH="$CE_REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}" python3 - "$CE_WORKER_ID" "${CE_TOOL_NAME:-unknown}" <<'PYMETER' || true
import sys
from dispatch_lib.budget import record_spend

record_spend(sys.argv[1], sys.argv[2], 0.0, source="wrapper-direct", estimated=True)
PYMETER
        # knotify surface (CEO 2026-08-20: dispatch notifications through our
        # notifier). Failures of a run notify loudly; adhoc completions ping
        # pass-class. Detached — never blocks the worker teardown path.
        KN=/Applications/Knotify.app/Contents/MacOS/knotify
        if [ -x "$KN" ]; then
            case "$phase" in
                errored|blocked)
                    ( "$KN" -c error -t "dispatch: ${CE_TOOL_NAME:-worker} $phase" -m "$CE_WORKER_ID — $error_summary" >/dev/null 2>&1 & ) ;;
                done)
                    ( "$KN" -c pass -t "dispatch: ${CE_TOOL_NAME:-worker} done" -m "$CE_WORKER_ID completed" >/dev/null 2>&1 & ) ;;
            esac
        fi
    fi

    # --- Self-healing + outcome recording ---
    # Centralized here so every run path (claude/codex/openai-compat/gemini)
    # gets it. On lane-fault errors (auth/rate_limit/network) the executor is
    # demoted into cooldown so the router reroutes; on success the cooldown is
    # cleared. task/needs_guidance/blocked are NOT lane faults (no demote).
    local log_file="$CE_DISPATCH_ROOT/logs/${CE_WORKER_ID}.log"
    PYTHONPATH="$CE_REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}" python3 - \
        "${CE_EXECUTOR_NAME:-${CE_TOOL_NAME:-unknown}}" "$CE_WORKER_ID" \
        "${CE_TIER:-unknown}" "$phase" "$log_file" <<'PY' 2>/dev/null || true
import sys, time, calendar, datetime
from dispatch_lib import lane_health, outcomes
from dispatch_lib.status_writer import read_status
executor, worker_id, tier, phase, log_file = sys.argv[1:6]
# Wave-2 FM-22: real duration from the worker's own started_at.
try:
    _st = read_status(worker_id) or {}
    _started = calendar.timegm(datetime.datetime.strptime(
        _st["started_at"], "%Y-%m-%dT%H:%M:%SZ").timetuple())
    duration_s = max(0.0, time.time() - _started)
except Exception:
    duration_s = 0.0
if phase == "done":
    lane_health.recover(executor)
    outcomes.record(worker_id, executor, tier, "success", duration_s, 0.0)
elif phase == "errored":
    try:
        text = open(log_file, errors="replace").read()[-4000:]
    except OSError:
        text = ""
    cls = lane_health.classify_failure(text)
    lane_health.demote(executor, cls)          # no-op for task-class
    outcomes.record(worker_id, executor, tier, cls, duration_s, 0.0)
else:
    # needs_guidance / blocked: task-level, not a lane fault.
    outcomes.record(worker_id, executor, tier, "task", duration_s, 0.0)
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
        echo "Worker $CE_WORKER_ID failed: missing terminal status token." >&2
        ce_finalize_status "errored" 4 "missing terminal status token"
        return 4
    fi
}

ce_parse_claude_log() {
    local log_file="$1"

    PYTHONPATH="$CE_REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}" python3 - \
        "$log_file" "$CE_WORKER_ID" <<'PY'
import sys

from dispatch_lib.status_writer import update_tokens
from dispatch_lib.stream_parser import (
    count_turns,
    extract_final_text,
    extract_token_usage,
    parse_stream_events,
)

log_file, worker_id = sys.argv[1:3]
with open(log_file, encoding="utf-8", errors="replace") as stream:
    events = list(parse_stream_events(stream))

usage = extract_token_usage(events)
turns = count_turns(events)
update_tokens(worker_id, usage["tokens_in"], usage["tokens_out"], turns)
print(extract_final_text(events))
PY
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
        --verbose
    )

    # Add provider-specific flags
    if [[ "$CE_BARE_MODE" -eq 1 ]]; then
        cmd+=(--bare)
    fi

    # Factory Workcells may supply a digest-bound capability manifest through
    # the foreground bridge. Restrict the actual Claude harness surface here;
    # a prompt-only tool policy is not enforcement. These variables are absent
    # for ordinary Dispatch work and therefore do not change other lanes.
    if [[ -n "${FACTORY_ALLOWED_TOOLS:-}" ]]; then
        cmd+=(--tools "$FACTORY_ALLOWED_TOOLS" --allowed-tools "$FACTORY_ALLOWED_TOOLS")
    fi
    if [[ "${FACTORY_DISABLE_SKILLS:-0}" -eq 1 ]]; then
        cmd+=(--disable-slash-commands)
    fi
    if [[ "${FACTORY_STRICT_MCP:-0}" -eq 1 ]]; then
        cmd+=(--strict-mcp-config --no-chrome)
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

    # Parse Claude Code JSONL so escaped terminal status text and telemetry are
    # interpreted structurally rather than grepped from raw JSON.
    local final_text=""
    if [[ -f "$log_file" ]]; then
        final_text="$(ce_parse_claude_log "$log_file")"
    fi

    # Map worker Status: tokens to documented exit codes.
    # Mapping:
    #   Status: DONE / DONE_WITH_CONCERNS  -> 0
    #   Status: NEEDS_GUIDANCE             -> 2
    #   Status: BLOCKED                    -> 3
    #   claude non-zero (no status token)  -> 4 (distinct from wrapper errors which use 1)
    #   no explicit status + clean exit    -> 4 (fail closed)
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
        --skip-git-repo-check
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

ce_run_agy() {
    if [[ -z "${CE_CWD:-}" ]]; then
        ce_parse_args "$@"
    fi

    ce_assemble_brief_with_packs
    ce_assemble_prompt

    local log_dir="$CE_DISPATCH_ROOT/logs"
    mkdir -p "$log_dir"
    local log_file="$log_dir/${CE_WORKER_ID}.log"
    local cmd=(agy --model "${AGY_MODEL:?AGY_MODEL is required}" --print-timeout "${AGY_PRINT_TIMEOUT:-10m}" --print "$CE_FINAL_PROMPT")

    if [[ "$CE_READ_ONLY" -eq 0 ]]; then
        cmd+=(--dangerously-skip-permissions --mode accept-edits)
    fi

    if [[ "$CE_DRY_RUN" -eq 1 ]]; then
        echo "DRY RUN - Would execute AGY model: $AGY_MODEL"
        return 0
    fi

    local exit_code=0
    if [[ -n "$CE_CWD" ]]; then
        (cd "$CE_CWD" && "${cmd[@]}") 2>&1 | tee "$log_file" || exit_code=$?
    else
        "${cmd[@]}" 2>&1 | tee "$log_file" || exit_code=$?
    fi
    rm -f "$CE_ASSEMBLED_BRIEF"

    if [[ $exit_code -ne 0 ]]; then
        ce_finalize_status "errored" 4 "agy exited with code $exit_code"
        return 4
    fi
    ce_finalize_from_text "$(cat "$log_file")"
}

ce_run_kilo() {
    if [[ -z "${CE_CWD:-}" ]]; then
        ce_parse_args "$@"
    fi

    ce_assemble_brief_with_packs
    ce_assemble_prompt

    local log_dir="$CE_DISPATCH_ROOT/logs"
    mkdir -p "$log_dir"
    local log_file="$log_dir/${CE_WORKER_ID}.log"
    local cmd=(kilo run --model "${KILO_MODEL:?KILO_MODEL is required}" --dir "$CE_CWD")
    if [[ "$CE_READ_ONLY" -eq 0 ]]; then
        cmd+=(--auto)
    fi
    cmd+=("$CE_FINAL_PROMPT")

    if [[ "$CE_DRY_RUN" -eq 1 ]]; then
        echo "DRY RUN - Would execute Kilo model: $KILO_MODEL"
        return 0
    fi

    local exit_code=0
    "${cmd[@]}" 2>&1 | tee "$log_file" || exit_code=$?
    rm -f "$CE_ASSEMBLED_BRIEF"
    if [[ $exit_code -ne 0 ]]; then
        ce_finalize_status "errored" 4 "kilo exited with code $exit_code"
        return 4
    fi
    ce_finalize_from_text "$(cat "$log_file")"
}

ce_run_kimi() {
    if [[ -z "${CE_CWD:-}" ]]; then
        ce_parse_args "$@"
    fi

    ce_assemble_brief_with_packs
    ce_assemble_prompt

    local log_dir="$CE_DISPATCH_ROOT/logs"
    mkdir -p "$log_dir"
    local log_file="$log_dir/${CE_WORKER_ID}.log"
    local cmd=(kimi --model "${KIMI_MODEL:?KIMI_MODEL is required}" --prompt "$CE_FINAL_PROMPT")

    if [[ "$CE_DRY_RUN" -eq 1 ]]; then
        echo "DRY RUN - Would execute Kimi K3 through the Kimi CLI alias: $KIMI_MODEL"
        return 0
    fi

    local exit_code=0
    if [[ -n "$CE_CWD" ]]; then
        (cd "$CE_CWD" && "${cmd[@]}") 2>&1 | tee "$log_file" || exit_code=$?
    else
        "${cmd[@]}" 2>&1 | tee "$log_file" || exit_code=$?
    fi
    rm -f "$CE_ASSEMBLED_BRIEF"
    if [[ $exit_code -ne 0 ]]; then
        ce_finalize_status "errored" 4 "Kimi CLI exited with code $exit_code"
        return 4
    fi
    ce_finalize_from_text "$(cat "$log_file")"
}

# Canonical GLM executor path: Z.AI ZCode (`zcode -p`), per docs/ZCODE.md.
ce_run_zcode() {
    if [[ -z "${CE_CWD:-}" ]]; then
        ce_parse_args "$@"
    fi

    ce_assemble_brief_with_packs
    ce_assemble_prompt
    # zcode's model can drift languages; the status parser needs this exact token.
    CE_FINAL_PROMPT+=$'\n\nOutput contract: your final line must be exactly "Status: DONE" or "Status: FAIL", in English.'

    local log_dir="$CE_DISPATCH_ROOT/logs"
    mkdir -p "$log_dir"
    local log_file="$log_dir/${CE_WORKER_ID}.log"

    local zcode_bin="${ZCODE_BIN:-}"
    if [[ -z "$zcode_bin" ]]; then
        local candidate
        for candidate in "$CE_SCRIPT_DIR/../zcode" "$HOME/.local/share/pushing-dispatch/repo/bin/zcode" "$(command -v zcode 2>/dev/null || true)"; do
            if [[ -n "$candidate" && -x "$candidate" ]]; then
                zcode_bin="$candidate"
                break
            fi
        done
    fi
    if [[ -z "$zcode_bin" ]]; then
        ce_finalize_status "errored" 69 "zcode binary not found (set ZCODE_BIN)"
        return 69
    fi

    local cmd=("$zcode_bin" -p "$CE_FINAL_PROMPT")
    if [[ -n "$CE_CWD" ]]; then
        cmd+=(--cwd "$CE_CWD")
    fi

    if [[ "$CE_DRY_RUN" -eq 1 ]]; then
        echo "DRY RUN - Would execute ZCode (GLM ${ZCODE_MODEL:-glm-5.3})"
        return 0
    fi

    local exit_code=0
    "${cmd[@]}" 2>&1 | tee "$log_file" || exit_code=$?
    rm -f "$CE_ASSEMBLED_BRIEF"
    if [[ $exit_code -ne 0 ]]; then
        ce_finalize_status "errored" 4 "zcode exited with code $exit_code"
        return 4
    fi
    ce_finalize_from_text "$(cat "$log_file")"
}

# DeepSeek Harness (dsh) one-shot lane; model/provider come from ~/.dsh/settings.yaml.
ce_run_dsh() {
    if [[ -z "${CE_CWD:-}" ]]; then
        ce_parse_args "$@"
    fi

    ce_assemble_brief_with_packs
    ce_assemble_prompt

    local log_dir="$CE_DISPATCH_ROOT/logs"
    mkdir -p "$log_dir"
    local log_file="$log_dir/${CE_WORKER_ID}.log"
    local cmd=(dsh --profile "${DSH_PROFILE:-headless}" "$CE_FINAL_PROMPT")

    if [[ "$CE_DRY_RUN" -eq 1 ]]; then
        echo "DRY RUN - Would execute dsh profile ${DSH_PROFILE:-headless}"
        return 0
    fi

    local exit_code=0
    if [[ -n "$CE_CWD" ]]; then
        (cd "$CE_CWD" && "${cmd[@]}") 2>&1 | tee "$log_file" || exit_code=$?
    else
        "${cmd[@]}" 2>&1 | tee "$log_file" || exit_code=$?
    fi
    rm -f "$CE_ASSEMBLED_BRIEF"
    if [[ $exit_code -ne 0 ]]; then
        ce_finalize_status "errored" 4 "dsh exited with code $exit_code"
        return 4
    fi
    ce_finalize_from_text "$(cat "$log_file")"
}

ce_run_grok() {
    if [[ -z "${CE_CWD:-}" ]]; then
        ce_parse_args "$@"
    fi

    ce_assemble_brief_with_packs
    ce_assemble_prompt

    local log_dir="$CE_DISPATCH_ROOT/logs"
    mkdir -p "$log_dir"
    local log_file="$log_dir/${CE_WORKER_ID}.log"
    local prompt_file
    prompt_file="$(mktemp "${TMPDIR:-/tmp}/dispatch-grok-prompt-XXXXXX")"
    printf '%s\n' "$CE_FINAL_PROMPT" > "$prompt_file"
    local cmd=(
        grok --model "${GROK_MODEL:?GROK_MODEL is required}"
        --cwd "$CE_CWD"
        --prompt-file "$prompt_file"
        --output-format plain
        --max-turns "${GROK_MAX_TURNS:-25}"
        --no-subagents
        --no-memory
        --no-auto-update
    )

    if [[ "$CE_READ_ONLY" -eq 0 ]]; then
        cmd+=(--permission-mode bypassPermissions --sandbox workspace)
    else
        cmd+=(--permission-mode plan --sandbox read-only)
    fi

    if [[ "$CE_DRY_RUN" -eq 1 ]]; then
        echo "DRY RUN - Would execute Grok model: $GROK_MODEL"
        rm -f "$prompt_file" "$CE_ASSEMBLED_BRIEF"
        return 0
    fi

    local exit_code=0
    "${cmd[@]}" 2>&1 | tee "$log_file" || exit_code=$?
    rm -f "$prompt_file" "$CE_ASSEMBLED_BRIEF"
    if [[ $exit_code -ne 0 ]]; then
        ce_finalize_status "errored" 4 "grok exited with code $exit_code"
        return 4
    fi
    ce_finalize_from_text "$(cat "$log_file")"
}

ce_run_gjc() {
    if [[ -z "${CE_CWD:-}" ]]; then
        ce_parse_args "$@"
    fi
    ce_assemble_brief_with_packs
    ce_assemble_prompt
    local log_dir="$CE_DISPATCH_ROOT/logs"
    mkdir -p "$log_dir"
    local log_file="$log_dir/${CE_WORKER_ID}.log"
    local cmd=(gjc --model "${GJC_MODEL:?GJC_MODEL is required}" --no-session --no-title -p "$CE_FINAL_PROMPT")
    local exit_code=0
    if [[ "$CE_DRY_RUN" -eq 1 ]]; then
        echo "DRY RUN - Would execute GJC model: $GJC_MODEL"
        return 0
    fi
    if [[ -n "$CE_CWD" ]]; then
        (cd "$CE_CWD" && "${cmd[@]}") 2>&1 | tee "$log_file" || exit_code=$?
    else
        "${cmd[@]}" 2>&1 | tee "$log_file" || exit_code=$?
    fi
    rm -f "$CE_ASSEMBLED_BRIEF"
    if [[ $exit_code -ne 0 ]]; then
        ce_finalize_status "errored" 4 "gjc exited with code $exit_code"
        return 4
    fi
    ce_finalize_from_text "$(cat "$log_file")"
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

messages = []
_system = os.environ.get("OPENAI_COMPAT_SYSTEM", "").strip()
if _system:
    messages.append({"role": "system", "content": _system})
messages.append({"role": "user", "content": prompt})
body = {
    "model": model,
    "messages": messages,
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

actual_model = data.get("model")
expected_response_model = os.environ.get("OPENAI_COMPAT_EXPECT_RESPONSE_MODEL", "").strip()
if expected_response_model and actual_model != expected_response_model:
    print(
        "response model identity mismatch: "
        f"expected {expected_response_model!r}, got {actual_model!r}",
        file=sys.stderr,
    )
    raise SystemExit(1)

print(json.dumps({
    "type": "system",
    "model": actual_model or model,
    "provider": os.environ.get("CE_TOOL_NAME", "openai-compatible"),
}))

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

ce_verify_pi_local_identity() {
    local health_url="${PI_LOCAL_HEALTH_URL:?PI_LOCAL_HEALTH_URL is required}"
    local expected_model="${PI_LOCAL_EXPECT_MODEL:?PI_LOCAL_EXPECT_MODEL is required}"
    # Studio/proxy catalogs list many models; require expected id present and loaded
    # when the endpoint reports a loaded flag (sticky Ornith on :8890).
    python3 - "$health_url" "$expected_model" <<'PY'
import json
import sys
import urllib.request

url, expected = sys.argv[1:3]
try:
    with urllib.request.urlopen(url, timeout=5) as response:
        payload = json.loads(response.read().decode("utf-8"))
except Exception:
    print(
        f"model identity mismatch: expected {expected!r}, endpoint identity unavailable",
        file=sys.stderr,
    )
    raise SystemExit(1)

rows = [item for item in payload.get("data", payload.get("models", [])) if isinstance(item, dict)]
match = None
for item in rows:
    mid = str(item.get("id") or item.get("model") or item.get("name") or "")
    if mid == expected or mid == f"{expected}:latest":
        match = item
        break
if match is None:
    ids = sorted(
        str(i.get("id") or i.get("model") or i.get("name"))
        for i in rows
        if (i.get("id") or i.get("model") or i.get("name"))
    )
    print(
        f"model identity mismatch: expected {expected!r} present, catalog={ids!r}",
        file=sys.stderr,
    )
    raise SystemExit(1)
# If Studio reports loaded flags, require the expected model be the resident one.
if "loaded" in match and match.get("loaded") is not True:
    print(
        f"model identity mismatch: {expected!r} present but loaded={match.get('loaded')!r}",
        file=sys.stderr,
    )
    raise SystemExit(1)
PY
}

# Extract product tokens from DISPATCH_PRODUCT_TOKENS or the assembled brief.
# "none" / "-" / product_class: chat disables the gate.
ce_resolve_product_tokens() {
    local tokens="${DISPATCH_PRODUCT_TOKENS:-}"
    local cls="${DISPATCH_PRODUCT_CLASS:-}"
    if [[ -z "$tokens" && -n "${CE_FINAL_PROMPT:-}" ]]; then
        tokens="$(printf '%s\n' "$CE_FINAL_PROMPT" | sed -nE 's/^[[:space:]]*[Pp]roduct[_ ]?[Tt]okens?:[[:space:]]*//p; s/^[[:space:]]*PRODUCT_TOKENS=//p' | head -1 | tr -d '\r')"
        if [[ -z "$cls" ]]; then
            cls="$(printf '%s\n' "$CE_FINAL_PROMPT" | sed -nE 's/^[[:space:]]*[Pp]roduct[_ ]?[Cc]lass:[[:space:]]*//p' | head -1 | tr -d '\r' | tr '[:upper:]' '[:lower:]')"
        fi
        if [[ -z "$tokens" ]]; then
            tokens="$(printf '%s\n' "$CE_FINAL_PROMPT" | grep -oE '\b(ULTRAQA_[A-Z0-9_]+|MEASURE_OK|PING_OK)\b' | sort -u | paste -sd, - || true)"
        fi
    fi
    tokens="$(printf '%s' "$tokens" | tr -d '[:space:]')"
    if [[ "$cls" == "chat" || "$tokens" == "none" || "$tokens" == "-" ]]; then
        DISPATCH_PRODUCT_TOKENS_RESOLVED=""
        return 0
    fi
    DISPATCH_PRODUCT_TOKENS_RESOLVED="$tokens"
}

# After Status: DONE, require at least one declared product token in log or receipt.
ce_require_product_tokens() {
    local blob="$1"
    ce_resolve_product_tokens
    local tokens="${DISPATCH_PRODUCT_TOKENS_RESOLVED:-}"
    if [[ -z "$tokens" ]]; then
        return 0
    fi
    local IFS=','
    local t found=0
    for t in $tokens; do
        [[ -z "$t" ]] && continue
        if printf '%s' "$blob" | grep -Fq -- "$t"; then
            found=1
            break
        fi
    done
    if [[ $found -eq 0 ]]; then
        echo "Worker $CE_WORKER_ID failed: missing product token(s) [$tokens] (Status alone is not enough)." >&2
        ce_finalize_status "errored" 4 "missing product token(s): $tokens"
        return 4
    fi
    echo "Worker $CE_WORKER_ID: product token gate passed ($tokens)" >&2
    return 0
}

# Short generation canary against PI_LOCAL_BASE_URL (proxy path Dispatch uses).
# On failure, optional raw diagnostic via PI_LOCAL_RAW_DIAG_URL.
ce_pi_local_gen_canary() {
    local base="${PI_LOCAL_BASE_URL:-}"
    local model="${PI_LOCAL_MODEL:-}"
    local marker="${PI_LOCAL_GEN_CANARY_MARKER:-PING_OK}"
    local timeout="${PI_LOCAL_GEN_CANARY_TIMEOUT:-25}"
    if [[ -z "$base" || -z "$model" ]]; then
        echo "gen canary skip: missing PI_LOCAL_BASE_URL or PI_LOCAL_MODEL" >&2
        return 0
    fi
    local url="${base%/}/chat/completions"
    local body
    body="$(python3 -c 'import json,sys; print(json.dumps({"model":sys.argv[1],"messages":[{"role":"user","content":sys.argv[2]}],"max_tokens":16,"temperature":0}))' "$model" "Reply with exactly: $marker")"
    local attempt=1 max_attempts=2 out=""
    while [[ $attempt -le $max_attempts ]]; do
        out="$(curl -sS --max-time "$timeout" -H 'Content-Type: application/json' -d "$body" "$url" 2>/dev/null || true)"
        if printf '%s' "$out" | python3 -c 'import sys,json
try:
 d=json.load(sys.stdin)
 # Model-identity assertion (COO UltraQA 2026-08-23, COO-004): in the
 # dual-resident no-switching architecture a misroute returns HTTP 200
 # served by the WRONG model — invisible to status codes. Fail the canary
 # unless the response model matches the requested id (prefix-match absorbs
 # llama.cpp alias suffix variants).
 rm=str(d.get("model") or "")
 rq=sys.argv[1]
 if rm and rq and not rm.startswith(rq.split(":")[0]) and rq not in rm:
  raise SystemExit(1)
 m=(d.get("choices") or [{}])[0].get("message",{}) or {}
 c=(m.get("content") or "")+(m.get("reasoning_content") or "")
 raise SystemExit(0 if str(c).strip() else 1)
except SystemExit:
 raise
except Exception:
 raise SystemExit(1)' "$model" 2>/dev/null; then
            echo "gen canary PASS: proxy $url produced content" >&2
            return 0
        fi
        attempt=$((attempt+1))
        sleep 1
    done
    echo "gen canary FAIL: proxy path did not return content within ${timeout}s x${max_attempts}" >&2
    local raw="${PI_LOCAL_RAW_DIAG_URL:-}"
    if [[ -n "$raw" ]]; then
        local raw_out
        raw_out="$(curl -sS --max-time 20 -H 'Content-Type: application/json' -d "$body" "${raw%/}/chat/completions" 2>/dev/null || true)"
        if printf '%s' "$raw_out" | python3 -c 'import sys,json
try:
 d=json.load(sys.stdin)
 m=(d.get("choices") or [{}])[0].get("message",{}) or {}
 c=(m.get("content") or "")+(m.get("reasoning_content") or "")
 raise SystemExit(0 if str(c).strip() else 1)
except Exception:
 raise SystemExit(1)' 2>/dev/null; then
            echo "gen canary DIAG: raw llama OK — Studio/proxy path is the problem (restart unsloth-studio + unsloth-openai-proxy)" >&2
        else
            echo "gen canary DIAG: raw llama also failed — model/server issue" >&2
        fi
    fi
    return 1
}

# Merge Pi stdout log + optional cwd receipt for dual-path Status finalize.
# Receipt path: $cwd/.dispatch-leaf-status (last line should be Status: DONE).
# Product-token hard gate when tokens declared (see ce_require_product_tokens).
ce_finalize_from_pi_local_artifacts() {
    local log_file="$1"
    local cwd="$2"
    local blob=""
    if [[ -f "$log_file" ]]; then
        blob="$(cat "$log_file")"
    fi
    local receipt="${cwd%/}/.dispatch-leaf-status"
    if [[ -f "$receipt" ]]; then
        echo "Worker $CE_WORKER_ID: merging leaf status receipt $receipt" >&2
        blob+=$'\n'"$(cat "$receipt")"
    fi
    # Status gate first
    local st_rc=0
    ce_finalize_from_text "$blob" || st_rc=$?
    if [[ $st_rc -ne 0 ]]; then
        return $st_rc
    fi
    # Product-token layer only on DONE green
    if echo "$blob" | grep -Eq '^[[:space:]*_`#>-]*Status:[[:space:]]*\*?\*?DONE(_WITH_CONCERNS)?\b'; then
        if ! ce_require_product_tokens "$blob"; then
            return 4
        fi
    fi
    return 0
}

ce_run_pi_local() {
    if [[ -z "${CE_CWD:-}" ]]; then
        ce_parse_args "$@"
    fi

    ce_assemble_brief_with_packs
    ce_assemble_prompt

    # Reinforce terminal protocol for Ornith/Pi leaves (stdout + dual receipt).
    CE_FINAL_PROMPT="${CE_FINAL_PROMPT}"$'\n\n'"MANDATORY finalize: print Status: DONE (or DONE_WITH_CONCERNS / NEEDS_GUIDANCE / BLOCKED) on its own final line. ALSO overwrite .dispatch-leaf-status in the working directory with that same single Status line (dual finalize if stdout capture fails)."

    local log_dir="$CE_DISPATCH_ROOT/logs"
    mkdir -p "$log_dir"
    local log_file="$log_dir/${CE_WORKER_ID}.log"
    # Skills / context progressive disclosure:
    # - progressive (default for Ornith): Pi injects skill name+description+path only;
    #   model `read`s full SKILL.md when needed. Skills live under PI_LOCAL_AGENT_DIR/skills.
    # - off: --no-skills (legacy slim leaf)
    # - full: same as progressive (Pi format is already progressive; kept as alias)
    local skills_mode="${PI_LOCAL_SKILLS_MODE:-off}"
    local context_mode="${PI_LOCAL_CONTEXT_FILES:-off}"
    local cmd=(
        pi
        --provider "${PI_LOCAL_PROVIDER:?PI_LOCAL_PROVIDER is required}"
        --model "${PI_LOCAL_MODEL:?PI_LOCAL_MODEL is required}"
        --mode text
        --thinking off
        --no-session
        --no-extensions
        --no-prompt-templates
        --tools "${PI_LOCAL_TOOLS:-read,bash,edit,write,grep,find,ls}"
        --append-system-prompt "${OPENAI_COMPAT_SYSTEM:-}"
        --print "$CE_FINAL_PROMPT"
    )
    if [[ "$skills_mode" == "off" ]]; then
        cmd+=(--no-skills)
    fi
    if [[ "$context_mode" == "off" ]]; then
        cmd+=(--no-context-files)
    fi

    if [[ "$CE_DRY_RUN" -eq 1 ]]; then
        echo "DRY RUN - Would execute Pi local model: $PI_LOCAL_PROVIDER/$PI_LOCAL_MODEL"
        echo "Agent config: $PI_LOCAL_AGENT_DIR"
        return 0
    fi

    if [[ ! -f "$PI_LOCAL_AGENT_DIR/models.json" ]]; then
        echo "Missing Pi local model registry: $PI_LOCAL_AGENT_DIR/models.json" >&2
        ce_finalize_status "errored" 4 "missing Pi local model registry"
        return 4
    fi

    if ! ce_verify_pi_local_identity; then
        rm -f "$CE_ASSEMBLED_BRIEF"
        ce_finalize_status "errored" 4 "Pi local endpoint model identity mismatch"
        return 4
    fi

    # Pre-start generation canary (proxy path). Refuse leaf if gen is dead.
    if [[ "${PI_LOCAL_GEN_CANARY:-0}" == "1" ]]; then
        if ! ce_pi_local_gen_canary; then
            rm -f "$CE_ASSEMBLED_BRIEF"
            ce_finalize_status "errored" 4 "Pi local gen canary failed (proxy completions unhealthy)"
            return 4
        fi
    fi

    local runtime_agent_dir="$PI_LOCAL_AGENT_DIR"
    local temporary_agent_dir=""
    if [[ -n "${PI_LOCAL_BASE_URL:-}" ]]; then
        temporary_agent_dir="$(mktemp -d "${TMPDIR:-/tmp}/dispatch-pi-agent-XXXXXX")"
        # Copy registry files; re-link skills so progressive catalog survives the temp dir.
        cp -R "$PI_LOCAL_AGENT_DIR/." "$temporary_agent_dir/"
        if [[ -d "$PI_LOCAL_AGENT_DIR/skills" ]]; then
            rm -rf "$temporary_agent_dir/skills"
            ln -sfn "$PI_LOCAL_AGENT_DIR/skills" "$temporary_agent_dir/skills"
        fi
        python3 - "$temporary_agent_dir/models.json" "$PI_LOCAL_PROVIDER" "$PI_LOCAL_BASE_URL" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
provider = sys.argv[2]
base_url = sys.argv[3]
payload = json.loads(path.read_text(encoding="utf-8"))
payload["providers"][provider]["baseUrl"] = base_url
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
        runtime_agent_dir="$temporary_agent_dir"
    fi

    # Line-buffer when GNU stdbuf/gstdbuf exists (macOS often lacks it).
    local buf_prefix=()
    if command -v stdbuf >/dev/null 2>&1; then
        buf_prefix=(stdbuf -oL -eL)
    elif command -v gstdbuf >/dev/null 2>&1; then
        buf_prefix=(gstdbuf -oL -eL)
    fi

    local exit_code=0
    # Clear dual-path receipt so a stale Status cannot green a failed run.
    rm -f "${CE_CWD%/}/.dispatch-leaf-status"
    # Empty-log early fail: if still 0 bytes after N seconds, kill the Pi leaf (avoid full alarm 142).
    local empty_secs="${PI_LOCAL_EMPTY_LOG_SECONDS:-90}"
    local empty_wd_pid=""
    if [[ "${empty_secs}" -gt 0 ]]; then
        (
            sleep "$empty_secs"
            if [[ ! -s "$log_file" ]]; then
                echo "Worker $CE_WORKER_ID: empty-log watchdog fired after ${empty_secs}s (0-byte log) — killing Pi leaf" >&2
                pkill -f "pi --provider ${PI_LOCAL_PROVIDER}" 2>/dev/null || true
            fi
        ) &
        empty_wd_pid=$!
    fi
    (
        cd "$CE_CWD"
        export PYTHONUNBUFFERED=1
        # Pi exposes no max-turns option. A process alarm bounds the local leaf.
        # buf_prefix + --mode text: reduce empty-log false exit-4 on multi-tool jobs.
        PI_CODING_AGENT_DIR="$runtime_agent_dir" \
            perl -e 'alarm shift; exec @ARGV' "${PI_LOCAL_TIMEOUT_SECONDS:-300}" \
            "${buf_prefix[@]}" "${cmd[@]}"
    ) 2>&1 | tee "$log_file" || exit_code=$?
    if [[ -n "$empty_wd_pid" ]]; then
        kill "$empty_wd_pid" 2>/dev/null || true
        wait "$empty_wd_pid" 2>/dev/null || true
    fi
    if [[ $exit_code -ne 0 && ! -s "$log_file" ]]; then
        echo "Worker $CE_WORKER_ID: Pi local empty log + non-zero exit (likely hang/alarm 142 or gen path dead)." >&2
    fi
    if [[ -n "$temporary_agent_dir" ]]; then
        rm -rf "$temporary_agent_dir"
    fi
    rm -f "$CE_ASSEMBLED_BRIEF"

    if [[ $exit_code -ne 0 ]]; then
        echo "Worker $CE_WORKER_ID: Pi local harness exited with code $exit_code." >&2
        ce_finalize_status "errored" 4 "Pi local harness exited with code $exit_code"
        return 4
    fi

    if ! ce_verify_pi_local_identity; then
        ce_finalize_status "errored" 4 "Pi local endpoint model identity changed during work"
        return 4
    fi

    ce_finalize_from_pi_local_artifacts "$log_file" "$CE_CWD"
}

ce_run_nuc_ondemand() {
    if [[ -z "${CE_CWD:-}" ]]; then
        ce_parse_args "$@"
    fi

    ce_assemble_brief_with_packs
    ce_assemble_prompt

    local log_dir="$CE_DISPATCH_ROOT/logs"
    local receipt_dir="$CE_DISPATCH_ROOT/receipts/nuc-workcells"
    mkdir -p "$log_dir" "$receipt_dir"
    local log_file="$log_dir/${CE_WORKER_ID}.log"
    local receipt_file="$receipt_dir/${CE_WORKER_ID}.json"
    local prompt_file
    prompt_file="$(mktemp "${TMPDIR:-/tmp}/dispatch-nuc-workcell-prompt-XXXXXX")"
    printf '%s\n' "$CE_FINAL_PROMPT" > "$prompt_file"

    local args=(
        --profile "${NUC_WORKCELL_PROFILE:?NUC_WORKCELL_PROFILE is required}"
        --prompt-file "$prompt_file"
        --cwd "$CE_CWD"
        --log-file "$log_file"
        --receipt-file "$receipt_file"
    )
    if [[ "$CE_DRY_RUN" -eq 1 ]]; then
        args+=(--dry-run)
    fi

    local exit_code=0
    PYTHONPATH="$CE_REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}" \
        python3 -m dispatch_lib.nuc_ondemand "${args[@]}" || exit_code=$?
    rm -f "$prompt_file" "$CE_ASSEMBLED_BRIEF"

    if [[ $exit_code -ne 0 ]]; then
        ce_finalize_status "errored" 4 "on-demand NUC workcell failed or could not prove restoration"
        return 4
    fi
    if [[ "$CE_DRY_RUN" -eq 1 ]]; then
        return 0
    fi
    ce_finalize_from_text "$(cat "$log_file")"
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
