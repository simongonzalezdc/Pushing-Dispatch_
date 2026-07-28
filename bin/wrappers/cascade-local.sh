#!/usr/bin/env bash
# cascade-local.sh — Three-tier local cascade for trivial/standard tasks.
#
# Tier 1: Dell 2B generates a response (free, ~3-5s)
# Tier 2: NUCBox 27B validates quality (free, ~5-10s)
# Tier 3: If 27B rejects → exit 1 → dispatch cooldown → cloud fallback
#
# This replaces the keyword-based router for tasks that both local boxes
# can handle. Cloud is ONLY hit when the 27B says the 2B's output is bad.

set -euo pipefail

# --- Config ---
DELL_BASE_URL="${XPS_OLLAMA_BASE_URL:-http://100.74.110.12:11434}"
DELL_MODEL="${XPS_OLLAMA_MODEL:-qwen35-2b-max}"
NUCBOX_URL="${NUCBOX_VALIDATOR_URL:-http://100.113.174.74:8892/v1/chat/completions}"
NUCBOX_MODEL="${NUCBOX_VALIDATOR_MODEL:-unsloth/Qwen3.6-27B-MTP-GGUF}"
DELL_MAX_TOKENS="${CASCADE_DELL_MAX_TOKENS:-512}"
VALIDATOR_MAX_TOKENS="${CASCADE_VALIDATOR_MAX_TOKENS:-16}"
DELL_TIMEOUT="${DELL_TIMEOUT:-60}"
NUCBOX_TIMEOUT="${NUCBOX_TIMEOUT:-120}"

# --- Parse args (same as other dispatch wrappers) ---
TASK=""
CWD=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --task)        TASK="$2"; shift 2 ;;
        --task-file)   TASK="$(cat "$2")"; shift 2 ;;
        --cwd)         CWD="$2"; shift 2 ;;
        --worker-id)   shift 2 ;;
        --mode)        shift 2 ;;
        --question-file) TASK="$(cat "$2")"; shift 2 ;;
        *)             shift ;;
    esac
done

if [[ -z "$TASK" ]]; then
    echo "Error: no task provided" >&2
    exit 2
fi

# --- Helpers: use each runtime's identity-preserving API ---
call_dell() {
    local base_url="${DELL_BASE_URL%/}" model="$1" content="$2" timeout="$3"
    local content_escaped
    content_escaped=$(printf '%s' "$content" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))")
    curl -s --max-time "$timeout" "$base_url/api/chat" \
        -H "Content-Type: application/json" \
        -d "{
            \"model\": \"$model\",
            \"messages\": [{\"role\": \"user\", \"content\": ${content_escaped}}],
            \"stream\": false,
            \"think\": false,
            \"options\": {\"temperature\": 0.2, \"num_predict\": $DELL_MAX_TOKENS}
        }" 2>/dev/null |
        EXPECTED_MODEL="$model" python3 -c 'import os,sys,json; data=json.load(sys.stdin); actual=data.get("model"); expected=os.environ["EXPECTED_MODEL"]; actual == expected or sys.exit(f"response model identity mismatch: expected {expected!r}, got {actual!r}"); print(data["message"]["content"])'
}

call_openai_model() {
    local url="$1" model="$2" content="$3" timeout="$4"
    local content_escaped
    content_escaped=$(printf '%s' "$content" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))")
    curl -s --max-time "$timeout" "$url" \
        -H "Content-Type: application/json" \
        -d "{
            \"model\": \"$model\",
            \"messages\": [{\"role\": \"user\", \"content\": ${content_escaped}}],
            \"stream\": false,
            \"temperature\": 0,
            \"max_tokens\": $VALIDATOR_MAX_TOKENS,
            \"chat_template_kwargs\": {\"enable_thinking\": false}
        }" 2>/dev/null |
        EXPECTED_MODEL="$model" python3 -c 'import os,sys,json; data=json.load(sys.stdin); actual=data.get("model"); expected=os.environ["EXPECTED_MODEL"]; actual == expected or sys.exit(f"response model identity mismatch: expected {expected!r}, got {actual!r}"); print(data["choices"][0]["message"]["content"])'
}

# --- TIER 1: Dell 2B generates ---
if [[ "${CASCADE_VERBOSE:-0}" == "1" ]]; then echo "[cascade] tier 1: Dell 2B generating..." >&2; fi
DELL_RESPONSE=$(call_dell "$DELL_MODEL" "$TASK" "$DELL_TIMEOUT") || {
    echo "[cascade] Dell 2B failed (timeout/error) — escalating to cloud" >&2
    exit 1
}

if [[ -z "$DELL_RESPONSE" || "${#DELL_RESPONSE}" -lt 10 ]]; then
    echo "[cascade] Dell 2B produced empty/short output — escalating to cloud" >&2
    exit 1
fi

# --- TIER 2: NUCBox 27B validates ---
VALIDATION_PROMPT="You are a quality validator. Given a task and a response, answer with just YES or NO.
If the response is correct, complete, and helpful, answer YES.
If the response is wrong, incomplete, a refusal, or gibberish, answer NO.

Task: $TASK

Response: $DELL_RESPONSE

Is this response acceptable? YES or NO:"

if [[ "${CASCADE_VERBOSE:-1}" == "1" ]]; then echo "[cascade] tier 2: NUCBox 27B validating..." >&2; fi
VERDICT=$(call_openai_model "$NUCBOX_URL" "$NUCBOX_MODEL" "$VALIDATION_PROMPT" "$NUCBOX_TIMEOUT") || {
    echo "[cascade] NUCBox validator unavailable — rejecting unvalidated 2B output" >&2
    exit 1
}

# --- TIER 3: Gate ---
if echo "$VERDICT" | grep -Eqi '^[[:space:]]*NO[[:space:]]*$'; then
    echo "[cascade] NUCBox 27B REJECTED 2B output — escalating to cloud" >&2
    exit 1
fi
if ! echo "$VERDICT" | grep -Eqi '^[[:space:]]*YES[[:space:]]*$'; then
    echo "[cascade] invalid validator verdict — rejecting unvalidated 2B output" >&2
    exit 1
fi

# --- Accept: output the 2B response ---
echo "$DELL_RESPONSE"
