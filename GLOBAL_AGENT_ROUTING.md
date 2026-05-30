# Global Agent Routing

Pushing Dispatch is the shared model-selection front door for coding agents.

## Install

```bash
cd /Users/simongonzalezdecruz/workspaces/Pushing-Dispatch_
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

Do not hand-pick Opus/Sonnet/Haiku/GPT/Kimi/Z.ai/MiniMax/Gemini/Kilo from vibes
when Dispatch is available. Dispatch owns the best-fit and cost-efficient choice
through `dispatch_matrix.toml`.

## Registered Local Surfaces

The routing rule is installed in:

- `~/.agents/rules/UNIVERSAL.md`
- `~/.codex/AGENTS.md`
- `~/.claude/CLAUDE.md`
- `~/.kimi/rules/kimi-rules.md`
- `~/.kilocode/rules/KiloApex.md`

## Pi / Other Machine Setup

Clone this repo to the target machine, copy or recreate `dispatch_matrix.toml`,
install provider CLIs/keys needed on that machine, then run:

```bash
bash bin/install-global-routing.sh
pushing-dispatch route --mode task --task "fix a typo"
```

For local-only Pi workers, make sure `codex`, `ollama`, and the selected local
model are installed, then use the `codex-oss` executor or let `auto` choose it
when the matrix is adjusted for that host.
