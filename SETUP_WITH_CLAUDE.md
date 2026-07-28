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
- Official Kimi CLI for Kimi K3 through the user's Kimi subscription; this is the only allowed subscription path.
- Ollama Cloud for a separate Kimi K3 lane. It stays unavailable until Ollama's live catalog exposes `kimi-k3`, and only this lane may become Hermes' native K3 provider.
- GJC for MiniMax M3.
- AGY for Gemini.
- Native Kilo CLI for free-only routing.
- Official Grok CLI for the `grok-build` / Grok 4.5 lane.
- LM Studio for the local lane.

Store credentials in the native login/key store or environment; never in the
matrix or docs.

Install and authenticate Grok with the official xAI package:

```bash
npm install -g @xai-official/grok
grok login --oauth
grok models
grok
```

Plain `grok` opens the interactive TUI. For one-shot/headless work, use
`grok -p "Explain this repo"`; headless hosts can authenticate with
`grok login --device-auth` or provide `XAI_API_KEY`.

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
