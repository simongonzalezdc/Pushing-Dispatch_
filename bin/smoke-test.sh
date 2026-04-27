#!/usr/bin/env bash
# smoke-test.sh - Verify the dispatch pipeline works end-to-end.
#
# Dispatches a trivial task to the cheapest available executor
# and verifies the worker completes. Cost: sub-$0.01.
#
# Exit 0 = pipeline works. Exit 1 = something is broken.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CLI="$REPO_ROOT/cli.py"
DISPATCH_ROOT="${DISPATCH_ROOT:-$HOME/.local/share/pushing-dispatch}"

echo "pushing-dispatch smoke test"
echo "======================"

# Check for dispatch matrix
MATRIX="$REPO_ROOT/dispatch_matrix.toml"
if [[ ! -f "$MATRIX" ]]; then
    echo "No dispatch_matrix.toml found. Copy from .example first:"
    echo "  cp dispatch_matrix.toml.example dispatch_matrix.toml"
    exit 1
fi

# Determine cheapest available executor
EXECUTOR=""
if [[ -n "${ANTHROPIC_API_KEY:-}" ]] || command -v claude &>/dev/null; then
    EXECUTOR="haiku"
elif [[ -n "${MOONSHOT_API_KEY:-}" ]]; then
    EXECUTOR="kimi"
elif [[ -n "${DEEPSEEK_API_KEY:-}" ]]; then
    EXECUTOR="deepseek"
else
    echo "No API keys configured. Set at least one of:"
    echo "  ANTHROPIC_API_KEY, MOONSHOT_API_KEY, or DEEPSEEK_API_KEY"
    exit 1
fi

echo "Using executor: $EXECUTOR"

# Create a trivial brief
BRIEF_FILE=$(mktemp "${TMPDIR:-/tmp}/smoke-brief-XXXXXX.md")
cat > "$BRIEF_FILE" << 'BRIEF'
---
title: Smoke test
---

# Task

This is a smoke test. Respond with exactly:

Status: DONE

Do not use any tools. Do not read or write any files.
Just output the status line above.
BRIEF

echo "Brief: $BRIEF_FILE"

# Create a temp working directory
WORK_DIR=$(mktemp -d "${TMPDIR:-/tmp}/smoke-work-XXXXXX")
cd "$WORK_DIR"
git init -q

echo "Dispatching..."

# Dispatch
WORKER_ID=$(python3 "$CLI" task start \
    --executor "$EXECUTOR" \
    --task-file "$BRIEF_FILE" \
    --cwd "$WORK_DIR" \
    --slug "smoke-test" \
    2>&1 | tail -1)

echo "Worker: $WORKER_ID"

# Poll for completion (max 120 seconds)
echo "Waiting for completion..."
TIMEOUT=120
ELAPSED=0
INTERVAL=5

while [[ $ELAPSED -lt $TIMEOUT ]]; do
    sleep $INTERVAL
    ELAPSED=$((ELAPSED + INTERVAL))

    PHASE=$(python3 "$CLI" status "$WORKER_ID" --field current_phase 2>/dev/null || echo "unknown")

    case "$PHASE" in
        done|errored|blocked|killed|needs_guidance)
            break
            ;;
        *)
            echo "  ${ELAPSED}s: phase=$PHASE"
            ;;
    esac
done

# Check result
FINAL_PHASE=$(python3 "$CLI" status "$WORKER_ID" --field current_phase 2>/dev/null || echo "unknown")

# Cleanup
rm -f "$BRIEF_FILE"
rm -rf "$WORK_DIR"

echo ""
echo "======================"

if [[ "$FINAL_PHASE" == "done" ]]; then
    echo "PASS: Worker completed successfully."
    echo "The dispatch pipeline is working."
    exit 0
elif [[ "$FINAL_PHASE" == "unknown" || "$FINAL_PHASE" == "starting" ]]; then
    echo "TIMEOUT: Worker did not complete within ${TIMEOUT}s."
    echo "Phase: $FINAL_PHASE"
    echo "Check: python3 cli.py status $WORKER_ID"
    exit 1
else
    echo "FAIL: Worker ended in phase: $FINAL_PHASE"
    echo "Check logs: python3 cli.py status $WORKER_ID"
    exit 1
fi
