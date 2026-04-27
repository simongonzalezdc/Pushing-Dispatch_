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
    CE_ASSEMBLED_BRIEF="$(mktemp "${TMPDIR:-/tmp}/dispatch-brief-XXXXXX.md")"

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
    prompt_file="$(mktemp "${TMPDIR:-/tmp}/dispatch-prompt-XXXXXX.md")"
    echo "$CE_FINAL_PROMPT" > "$prompt_file"

    # Build claude command
    local cmd=(
        claude
        -p "$prompt_file"
        --output-format stream-json
    )

    # Add provider-specific flags
    if [[ "$CE_BARE_MODE" -eq 1 ]]; then
        cmd+=(--bare)
    fi

    if [[ -n "$CE_CWD" ]]; then
        cmd+=(--cwd "$CE_CWD")
    fi

    if [[ "$CE_MAX_TURNS" -gt 0 ]]; then
        cmd+=(--max-turns "$CE_MAX_TURNS")
    fi

    if [[ "$CE_READ_ONLY" -eq 1 ]]; then
        cmd+=(--disallowed-tools "Write,Edit,MultiEdit,NotebookEdit")
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
    "${cmd[@]}" 2>&1 | tee "$log_file" || exit_code=$?

    # Clean up temp files
    rm -f "$prompt_file" "$CE_ASSEMBLED_BRIEF"

    # Map exit codes to dispatch status
    case $exit_code in
        0)
            echo "Worker $CE_WORKER_ID completed successfully."
            ;;
        1)
            echo "Worker $CE_WORKER_ID exited with error." >&2
            ;;
        *)
            echo "Worker $CE_WORKER_ID exited with code $exit_code." >&2
            ;;
    esac

    return $exit_code
}

# --- API key loading helpers ---

# Generic keychain loader (macOS). Falls back to env var.
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

    echo "Error: API key not found for $service/$account." >&2
    echo "Set $env_var env var, or store in macOS Keychain (service=$service, account=$account)." >&2
    return 1
}
