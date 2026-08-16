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
- **Canonical GLM harness is ZCode** (`zcode -p` / `zcode --prompt`), Z.AI’s own CLI. Model pin `glm-5.3`. Procedure: `docs/ZCODE.md` and `~/.agents/docs/ZCODE-GLM.md`. Do not teach agents to call GLM through Claude Code.
- `bin/claude-glm52` is **legacy** (Anthropic-compatible wrapper still used by the `zai-glm` executor until that lane is rewired onto ZCode).
- Do not send visual-QA / screenshot loops to ZCode unless the user asked for eyes. Dedicated vision lanes remain preferred for vision-critical work.
- When any model's primary search path fails or yields unusable results, retry through the globally configured DuckDuckGo `ddg` MCP. If DDG also fails, report the search failure; never fabricate results, URLs, or citations.
- GJC is the backup chat path: `gjc --model zai/glm-5.3` or `gjc --model minimax-code/minimax-m3`. Not the GLM harness. Canonical GLM is `zcode -p` — `docs/ZCODE.md`.
- `claude-minimax` is the direct MiniMax M3 fallback.
- Kimi K3 is split by access boundary: `kimi-k3-cli` always uses the official Kimi CLI subscription session, while `kimi-k3-ollama` uses only Ollama Cloud and remains unavailable until Ollama's live catalog exposes K3. Hermes may promote only the Ollama lane to its native main model; never exchange credentials or silently substitute lanes.
- Gemini models are exclusive to AGY (`agy-gemini-flash` only — 3.7 Flash is the sole allowed AGY model); Gemini CLI and legacy direct-API lanes are retired.
- Grok Build is the `grok-build` executor through xAI's official `grok` CLI, pinned to `grok-4.6`. It replaces retired Claude Opus-class work: hard implementation, deep architecture, adversarial review, breakout, and consult tiers prefer Grok. It is vision-capable, uses native OAuth or `XAI_API_KEY`, transports briefs by prompt file, and runs with explicit `workspace`/`read-only` sandbox profiles. Do not route through community Grok clients.
- Ordinary work remains GPT-5.6 Luna-first. Within Codex, retry an unusable Luna result with Terra high; use Sol only when justified, escalating low, medium, then high and stopping after high. Auto-routing cannot judge semantic answer quality. GPT-5.5, Codex OSS, NUCBox Gemma, and Anthropic Opus are retired.
- **Ornith sticky leaf (`unsloth-nucbox`):** free NUC coding/ops for **m3-class only** (bounded · localized · reversible · verifying). Never sole architect/critic/security/vision/web/breakout-top. Serialize jobs. Full YES/NO: fleet `launchpad/docs/agents/ORNITH-GUIDELINES.md` § Cloud-orchestrator card; pack `ornith-leaf`; `docs/ORCHESTRATING.md`.
- On-demand dual-load Qwen workcells on `:8892` stay **retired** while Ornith is the single big resident model. Dell Qwen 3.5 2B remains atomic mechanical only (with resident NUC validation where configured). Broad/risky, oversized, visual, breakout, consult, and long-context work stays on stronger cloud tiers.
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
