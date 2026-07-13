# Global Agent Routing

Pushing Dispatch is the shared model-selection front door for coding agents.

## Install

```bash
cd "$HOME/workspaces/pushing-dispatch"
bash bin/install-global-routing.sh
```

This installs:

- `~/.local/bin/pushing-dispatch`
- `~/.local/bin/dispatch`

Both commands point at this checkout and use `dispatch_matrix.toml`.

## First-time credential setup

Consolidate every provider key into the macOS Keychain service
`pushing-dispatch` so non-interactive dispatch subprocesses can reach them:

```bash
bash bin/sync-credentials.sh   # harvests .zshrc / goose / dopamine-depot / codex config
pushing-dispatch doctor        # shows which executors are actually reachable
```

`doctor` prints a live table of every executor's availability, cooldown state,
and any provider that needs re-login. Run it any time a lane misbehaves.

## Self-healing routing

`route` and `task start --executor auto` only ever return an executor that is
reachable right now. When a worker fails with an auth / rate-limit / network
error, that lane is demoted into a cooldown (persisted in `lane_health.json`)
and the router automatically reroutes to the next candidate; the lane recovers
on cooldown expiry or the next success. Genuine task failures are never treated
as lane faults. Routing uses ordered candidate lists per tier
(trivial / standard / hard / long-context / consult) from `[auto_route]`.

## Required Agent Policy

All coding agents should ask Dispatch before choosing a provider/model for
delegated, background, parallel, consult, or subagent work:

```bash
pushing-dispatch route --mode task --task "<brief>"
pushing-dispatch route --mode breakout --task "<brief>"
pushing-dispatch route --mode consult --task "<question>"
```

To launch a worker:

```bash
pushing-dispatch task start --executor auto --task "<brief>" --cwd "$PWD"
```

Do not hand-pick GPT/Kimi/Z.AI/MiniMax/Gemini/local models from vibes
when Dispatch is available. Dispatch owns the best-fit and cost-efficient choice
through `dispatch_matrix.toml`.

Current provider truth:

- Anthropic subscription lanes are retired and absent from the matrix.
- Claude Code defaults to Z.AI `glm-5.2` through `bin/claude-glm52`.
- GLM 5.2 has no vision capability. Dispatch must reject GLM for images, screenshots, video, rendered-UI inspection, and every other visual task.
- When any model's primary search path fails or yields unusable results, retry through the globally configured DuckDuckGo `ddg` MCP. If DDG also fails, report the search failure; never fabricate results, URLs, or citations.
- GJC is the backup: `gjc --model zai/glm-5.2` or `gjc --model minimax-code/minimax-m3`.
- `claude-minimax` is the direct MiniMax M3 fallback.
- Kimi K2.7 is the single `kimi-k27` lane, exclusive to native `kimi-cli` through its managed `kimi-for-coding` alias.
- Gemini models are exclusive to AGY (`agy-gemini-flash` and `agy-gemini-pro`); Gemini CLI and legacy direct-API lanes are retired.
- Codex uses the ChatGPT subscription: GPT-5.6 Luna for trivial work, Terra as the better-and-cheaper everyday replacement for GPT-5.5, and Sol for frontier hard/consult work. GPT-5.5, Codex OSS, and NUCBox Gemma are retired.
- Kilo is CLI-only and free-only: the durable lane is `kilo-free-auto` using `kilo/kilo-auto/free`. Never fall through to a paid Kilo model; rotating monthly `:free` models must be verified live before use.

## Registered Local Surfaces

The routing rule is installed in:

- `~/.agents/rules/UNIVERSAL.md`
- `~/.codex/AGENTS.md`
- `~/.claude/CLAUDE.md` (+ `~/.claude/settings.json` allow-lists `Bash(pushing-dispatch:*)` and `Bash(dispatch:*)` so calls never prompt)
- `~/.pi/agent/AGENTS.md`
- `~/.kimi/rules/kimi-rules.md`
- `~/.kilocode/rules/KiloApex.md`

## Pi / Other Machine Setup

Clone this repo to the target machine, copy or recreate `dispatch_matrix.toml`,
install provider CLIs/keys needed on that machine, then run:

```bash
bash bin/install-global-routing.sh
pushing-dispatch route --mode task --task "fix a typo"
```

For local-only hosts, define an explicit host-local executor in that host's
matrix (for example LM Studio or Ollama) and let `auto` select it. `codex-oss`
is retired and must not be restored as a generic fallback.
