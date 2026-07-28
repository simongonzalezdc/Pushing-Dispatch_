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

Do not hand-pick GPT/Kimi/Z.AI/MiniMax/Gemini/Grok/local models from vibes
when Dispatch is available. Dispatch owns the best-fit and cost-efficient choice
through `dispatch_matrix.toml`.

Current provider truth:

- Anthropic subscription lanes are retired and absent from the matrix.
- Claude Code defaults to Z.AI `glm-5.2` through `bin/claude-glm52`.
- GLM 5.2 has no vision capability. Dispatch must reject GLM for images, screenshots, video, rendered-UI inspection, and every other visual task.
- When any model's primary search path fails or yields unusable results, retry through the globally configured DuckDuckGo `ddg` MCP. If DDG also fails, report the search failure; never fabricate results, URLs, or citations.
- GJC is the backup: `gjc --model zai/glm-5.2` or `gjc --model minimax-code/minimax-m3`.
- `claude-minimax` is the direct MiniMax M3 fallback.
- Kimi K3 is split by access boundary: `kimi-k3-cli` always uses the official Kimi CLI subscription session, while `kimi-k3-ollama` uses only Ollama Cloud and remains unavailable until Ollama's live catalog exposes K3. Hermes may promote only the Ollama lane to its native main model; never exchange credentials or silently substitute lanes.
- Gemini models are exclusive to AGY (`agy-gemini-flash` and `agy-gemini-pro`); Gemini CLI and legacy direct-API lanes are retired.
- Grok Build is the `grok-build` executor through xAI's official `grok` CLI, pinned to `grok-4.5`. It replaces retired Claude Opus-class work: hard implementation, deep architecture, adversarial review, breakout, and consult tiers prefer Grok. It is vision-capable, uses native OAuth or `XAI_API_KEY`, transports briefs by prompt file, and runs with explicit `workspace`/`read-only` sandbox profiles. Do not route through community Grok clients.
- Ordinary work remains GPT-5.6 Luna-first. Within Codex, retry an unusable Luna result with Terra high; use Sol only when justified, escalating low, medium, then high and stopping after high. Auto-routing cannot judge semantic answer quality. GPT-5.5, Codex OSS, NUCBox Gemma, and Anthropic Opus are retired.
- Governed local Qwen work is available through Dispatch: Dell Qwen 3.5 2B for atomic mechanical work only with resident NUC validation; resident NUC Qwen 3.6 27B as a bounded fallback; and automatically admitted NUC workcells for bounded Qwen 3.5 35B general work, Qwen 3.5 27B review, and Qwen 3.6 35B coding. Deterministic routing ceilings are 24K, 5K, and 5K input tokens respectively. Broad/risky, oversized, visual, breakout, consult, and long-context work stays on its stronger existing tier.
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
install provider CLIs/keys needed on that machine (for Grok: `npm install -g @xai-official/grok` then `grok login --oauth`), then run:

```bash
bash bin/install-global-routing.sh
pushing-dispatch route --mode task --task "fix a typo"
```

For local-only hosts, define an explicit host-local executor in that host's
matrix (for example LM Studio or Ollama) and let `auto` select it. `codex-oss`
is retired and must not be restored as a generic fallback.
