# Customization Guide

Recipes for adapting ai-dispatch to your workflow.

## Adding a New Provider

### Step 1: Write a wrapper (20 lines)

Create `bin/wrappers/newprovider.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_exec.sh"

export CE_TOOL_NAME="newprovider"
export CE_BARE_MODE=1  # Third-party: brief-only context

# Load API key
KEY=$(ce_load_api_key "ai-dispatch" "newprovider_api_key" "NEWPROVIDER_API_KEY")
export ANTHROPIC_AUTH_TOKEN="$KEY"
export ANTHROPIC_BASE_URL="https://api.newprovider.com/anthropic"
export ANTHROPIC_MODEL="newprovider-model-v1"

export CE_MAX_TURNS="${CE_MAX_TURNS:-25}"

ce_parse_args "$@"
ce_run_claude
```

Make it executable: `chmod +x bin/wrappers/newprovider.sh`

### Step 2: Add a matrix entry

In `dispatch_matrix.toml`:

```toml
[executors.newprovider]
wrapper = "newprovider.sh"
provider = "newprovider"
model_id = "newprovider-model-v1"
allowed_modes = ["task"]
context_window = 128000
max_turns = 25
stall_threshold_seconds = 300
```

### Step 3: Add permissions (if using nested dispatch)

```toml
[nested_dispatch.permissions]
# Existing entries...
sonnet.newprovider = true
opus.newprovider = true
```

### Step 4: Test

```bash
python cli.py task start --executor newprovider --task "echo hello" --cwd /tmp
```

## Tuning Thinking Token Caps

Each executor has `default_thinking_tokens` and `thinking_hard_ceiling` in the matrix.

```toml
[executors.kimi-think]
default_thinking_tokens = 4000     # Default per-task
thinking_hard_ceiling = 8000       # Absolute maximum
```

To override per-task, set in the brief:

```yaml
---
thinking_tokens: 6000
---
```

Or pass via the wrapper: `--thinking 6000`

**Guidance:**
- 0: thinking disabled (mechanical work)
- 2000-4000: standard reasoning
- 4000-8000: complex problems
- 8000+: only for Opus on hard synthesis tasks

## Swapping the Brief-Pack Mechanism

The default pack mechanism uses `dispatch_packs/_registry.toml` to map names to files. You can replace this with any context strategy.

### Alternative: directory-based packs

Set `DISPATCH_PACKS_DIR` to a directory where pack files live. The wrapper resolves `includes: [foo]` to `$DISPATCH_PACKS_DIR/foo.md`.

### Alternative: URL-based packs

Modify `ce_assemble_brief_with_packs` in `_exec.sh` to fetch packs from a URL:

```bash
# In _exec.sh, replace the pack resolution loop
curl -sL "https://your-registry.com/packs/${pack_name}.md" >> "$CE_ASSEMBLED_BRIEF"
```

### Alternative: inline-only (no packs)

Remove the `includes:` processing from `_exec.sh`. Every brief carries its own full context. Simpler but more repetitive.

## Disabling Auto-Poll

Remove the hook entries from your Claude Code settings.json:

```json
{
  "hooks": {
    "SessionStart": [],
    "UserPromptSubmit": []
  }
}
```

### Re-enabling per-session

Start the polling loop manually:

```
/loop 90s /dispatch-poll
```

Or run a single poll:

```bash
python cli.py list --active && python cli.py completions && python cli.py questions
```

## Adjusting Nested Dispatch Depth Caps

### Via environment variable

```bash
export DISPATCH_MAX_DEPTH=3  # Allow 3 levels of nesting
```

### Via the matrix

```toml
[nested_dispatch]
max_depth = 2
```

### Ramp plan (recommended)

1. Start at `max_depth = 1`. Monitor spend with `python cli.py budget --tree`.
2. After 1 week with no cost anomalies, bump to 2.
3. After another week, bump to 3 (the design target).

## Adjusting the Permissions Matrix

Edit `[nested_dispatch.permissions]` in `dispatch_matrix.toml`.

**Rules to respect:**
- Never add self-dispatch (e.g., `sonnet.sonnet = true`). This creates unbounded cost spirals.
- Be cautious with metered-to-subscription pairs (e.g., `kimi.opus`). The metered parent's budget cannot account for the subscription child's hidden overhead.
- Leaf executors (haiku, local models) should not dispatch.

**To add a new permission:**

```toml
[nested_dispatch.permissions]
newprovider.haiku = true  # newprovider can dispatch haiku sub-workers
```

## Wiring Custom Hooks

### PreToolUse hook (validation)

```json
{
  "hooks": {
    "PreToolUse": [{
      "type": "command",
      "command": "python /path/to/your/validator.py",
      "timeout": 5000
    }]
  }
}
```

### Stop hook (cleanup)

```json
{
  "hooks": {
    "Stop": [{
      "type": "command",
      "command": "bash /path/to/cleanup.sh"
    }]
  }
}
```

**Important:** Custom hooks run for all Claude Code sessions, not just dispatch workers. If your hook should only apply to workers, check for the `DISPATCH_WORKER_ID` env var:

```bash
if [[ -z "${DISPATCH_WORKER_ID:-}" ]]; then
    exit 0  # Not a dispatch worker, skip
fi
```

## Customizing DISPATCH_ROOT

All dispatch artifacts live under `DISPATCH_ROOT`:

```
$DISPATCH_ROOT/
  status/          # Worker status JSON files
  logs/            # Worker log files
  questions/       # Question files from workers
  budget.jsonl     # Spend ledger
  session_registry.jsonl
  auto_poll_active_*  # Polling markers
```

Default: `~/.local/share/ai-dispatch/`

Override: `export DISPATCH_ROOT=/path/to/your/dir`

For multi-user setups, each user should have their own DISPATCH_ROOT.
