# Setup With Claude Code (GLM 5.2 Harness)

Claude Code is the shell/harness for GLM 5.2 on this machine. Anthropic
subscription models are not active Dispatch lanes.

## Install the Canonical Checkout

```bash
git clone https://git.kyanitelabs.tech/simon/pushing-dispatch.git "$HOME/workspaces/pushing-dispatch"
cd "$HOME/workspaces/pushing-dispatch"
chmod +x bin/claude-glm52 bin/wrappers/*.sh
```

Install or verify the global `pushing-dispatch` and `dispatch` entry points, and
make global `claude` resolve to `bin/claude-glm52`. Preserve the original Claude
Code binary as `claude-real` for harness maintenance only.

## Required Harnesses

- Codex CLI with the ChatGPT subscription for Luna, Terra, and Sol.
- Claude Code plus Z.AI credentials for GLM 5.2.
- Native Kimi CLI for Kimi K2.7.
- GJC for MiniMax M3.
- AGY for Gemini.
- Native Kilo CLI for free-only routing.
- LM Studio for the local lane.

Store credentials in the native login/key store or environment; never in the
matrix or docs.

## Verify

```bash
bash bin/check-prereqs.sh
pushing-dispatch validate-matrix dispatch_matrix.toml
python3 -m pytest -q
pushing-dispatch doctor --probe
```

Then confirm routing:

```bash
pushing-dispatch route --mode task --task "fix a typo"
pushing-dispatch route --mode task --task "implement the account recovery flow"
pushing-dispatch route --mode consult --task "review this architecture"
```

Expected tiers are Luna, Terra, and Sol. Visual tasks must never route to GLM.
Search failures must fall back to the global DuckDuckGo `ddg` MCP.
