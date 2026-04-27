# Installation Guide

## Prerequisites

### Required

- **Python 3.11+** -- the dispatch framework uses `tomllib` (stdlib in 3.11+)
- **Bash 4+** -- provider wrappers use bash 4 features (associative arrays, `${var,,}`).
  - **macOS gotcha:** macOS ships Bash 3.2 (Apple stopped updating it for licensing reasons). Install a current bash via Homebrew:
    ```bash
    brew install bash
    # Verify (will be at /opt/homebrew/bin/bash on Apple Silicon, /usr/local/bin/bash on Intel):
    /opt/homebrew/bin/bash --version
    ```
    Wrappers use `#!/usr/bin/env bash`, so they pick up whichever `bash` is first in `PATH`. Make sure Homebrew's bash is ahead of `/bin/bash`.
- **Git** -- worktree-based isolation requires git
- **Claude Code CLI** (`claude`) -- the harness that runs all providers
  - Install: `npm install -g @anthropic-ai/claude-code`
  - Or via Homebrew: `brew install claude-code`
  - Verify: `claude --version`

### Optional (for specific providers)

- **Kimi CLI** (`kimi-cli`) -- only needed if using Kimi's native mode (rare)
  - Install: `pip install kimi-cli`
- **Ollama** -- only needed for local model dispatch
  - Install: https://ollama.com/download

### Check your environment

```bash
bash bin/check-prereqs.sh
```

This script verifies all required tools are present and reports missing optionals.

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/YOUR_ORG/pushing-dispatch.git
cd pushing-dispatch
```

### 2. Configure the dispatch matrix

```bash
cp dispatch_matrix.toml.example dispatch_matrix.toml
```

Edit `dispatch_matrix.toml` to match your setup. At minimum, configure the executors for the providers you have API keys for.

### 3. Set API keys

**Anthropic (Claude):**
```bash
# Option A: Environment variable
export ANTHROPIC_API_KEY="sk-ant-api03-..."

# Option B: Claude Code's built-in auth
claude login
```

**Moonshot (Kimi):**
```bash
# Option A: Environment variable
export MOONSHOT_API_KEY="sk-..."

# Option B: macOS Keychain
security add-generic-password -s "pushing-dispatch" -a "moonshot_api_key" -w "sk-..."

# Option C: pass (password store)
pass insert pushing-dispatch/moonshot_api_key
```

**DeepSeek:**
```bash
# Same pattern as Moonshot
export DEEPSEEK_API_KEY="sk-..."
# or Keychain/pass with account "deepseek_api_key"
```

### API key lookup order

The wrapper checks in this order:
1. Environment variable (e.g., `MOONSHOT_API_KEY`)
2. macOS Keychain (service=`pushing-dispatch`, account=`<provider>_api_key`)
3. `pass` password store (`pushing-dispatch/<provider>_api_key`)

### 4. Run the smoke test

```bash
bash bin/smoke-test.sh
```

This dispatches a trivial task to your cheapest configured executor and verifies the full pipeline works. Cost: sub-$0.01.

### 5. (Optional) Set up auto-polling

Add the auto-poll hook to your Claude Code settings:

```json
{
  "hooks": {
    "SessionStart": [{
      "type": "command",
      "command": "bash /path/to/pushing-dispatch/hooks/auto_poll.sh"
    }],
    "UserPromptSubmit": [{
      "type": "command",
      "command": "bash /path/to/pushing-dispatch/hooks/auto_poll.sh"
    }]
  }
}
```

This automatically starts polling when you have active workers, and stops when they finish.

### 6. (Optional) Set DISPATCH_ROOT

By default, dispatch artifacts (status files, logs, budget ledger) live in `~/.local/share/pushing-dispatch/`. Override with:

```bash
export DISPATCH_ROOT="/path/to/your/dispatch/data"
```

## Platform Notes

### macOS

Full support. Keychain integration works natively.

### Linux

Full support. Use environment variables or `pass` for API keys (no Keychain).

### Windows (WSL)

Works under WSL2. Use environment variables for API keys. Native Windows is not tested.

## Obtaining API Keys

### Anthropic

1. Go to https://console.anthropic.com/
2. Create an account or sign in
3. Navigate to API Keys
4. Create a new key

Alternatively, use Claude Code's subscription auth: `claude login`.

### Moonshot (Kimi)

1. Go to https://platform.moonshot.cn/
2. Create an account
3. Navigate to API Keys in your dashboard
4. Create a new key

### DeepSeek

1. Go to https://platform.deepseek.com/
2. Create an account
3. Navigate to API Keys
4. Create a new key

## Verifying Your Setup

After installation, run through these checks:

1. `bash bin/check-prereqs.sh` -- all green
2. `bash bin/smoke-test.sh` -- dispatches and completes successfully
3. `python cli.py list` -- shows the smoke test worker (should be in `done` state)
4. `python cli.py budget` -- shows today's spend (should be minimal)

If any step fails, see [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).
