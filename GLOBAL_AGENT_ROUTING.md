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
- Kimi K3 is split by access boundary: `kimi-k3-cli` always uses the official Kimi CLI subscription session. The `kimi-k3-ollama` lane was attic'd 2026-08-20 and Ollama Cloud routes are policy-OUT in `SUBSCRIPTIONS.yaml` — do not restore it. Never exchange credentials or silently substitute lanes.
- Gemini models are exclusive to AGY (`agy-gemini-flash` only — 3.7 Flash is the sole allowed AGY model); Gemini CLI and legacy direct-API lanes are retired.
- Grok Build is the `grok-build` executor through xAI's official `grok` CLI, pinned to `grok-4.6`. It is vision-capable, uses native OAuth or `XAI_API_KEY`, transports briefs by prompt file, and runs with explicit `workspace`/`read-only` sandbox profiles. Do not route through community Grok clients. Since the 2026-08-24 local-first flip it is **explicit-only**: removed from every auto-route list; request it by name only (the OpenAI/Grok accounts end Sept 2026 wk1/wk2 — burn-down by direct request).
- Ordinary work is **local-first**: `nucbox-champion` is the default task/breakout executor and `nucbox-ornith` the default consult executor (auto_route, 2026-08-24). Codex (`codex-luna`/`codex-terra`/`codex-sol`) is explicit-only too — never auto-selected. Within an explicit Codex request, retry an unusable Luna result with Terra high; use Sol only when justified, escalating low, medium, then high and stopping after high. GPT-5.5, Codex OSS, NUCBox Gemma, and Anthropic Opus are retired.
- **Ornith sticky leaf (`unsloth-nucbox`):** RETIRED — replaced by the dual-resident executors below.
- On-demand dual-load Qwen workcells on `:8892`: RETIRED — replaced by `nucbox-ornith` on `:46381`.

## Local Model Executors (dual-resident, 2026-08-23)

Two local models run simultaneously on the NUC (Strix Halo, 96GB unified, 64GB GTT).
Both have FULL AGENT TOOLS via tokflint: bash, read/write/edit files, grep, find, code search.
Both are zero-cost. Both have vision. Both load in seconds.

**Route to `nucbox-champion` (Qwen3.8-27B, ~26 tok/s) when:**
- The task is ITERATIVE (same context resent across turns — coding sessions,
  agent tool loops, debug cycles, review-then-fix). Its 54x prompt cache means
  turn 2+ returns in 0.4s instead of 1.7s — this is its killer feature.
- The task needs >32k context (champion has 262k; ornith dispatch config is 32k).
- You want terse, factual, no-fluff output.
- The task is code review (certified 20/20 on the delegation card).
- You need a quick answer with no thinking delay (think-off default).

**Route to `nucbox-ornith` (Ornith-1.5-35B-A3B, ~55 tok/s) when:**
- The task is ONE-SHOT generation (analysis, summary, long document, essay).
  2x faster than champion on fresh-context generation.
- The task is math-heavy (97% GSM8K with thinking vs champion's 90%).
- You want a second opinion from a different model lineage.
- You want detailed, exploratory, conversational output.
- The champion is busy or you want to parallelize across local models.

**Route to cloud (not local) when:**
- Local lanes are saturated, in cooldown, or unavailable — the router walks the
  candidate list in order, so cloud lanes only fire after the local leads.
- The task is vision-critical (local vision works but cloud is better).
- Context exceeds what the locals carry — the long-context tier leads Kimi K3
  (1M window), not the NUC.

**Quick rule of thumb:** iterative → champion, one-shot → ornith, hard task →
ornith then champion, hard breakout → champion then ornith (all local first),
long-context → Kimi.
- Kilo defaults to **deepseek-v4-flash while account credit remains** ($50/mo, resets the 15th); the `kilo-free-auto` lane (`kilo/kilo-auto/free`) is used only once credits are exhausted. Kilo can also back up Kimi-K3 when the canonical Kimi account runs out of usage — check balance before heavy fan-outs late in the cycle. Rotating monthly `:free` models must be verified live before use.

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

## Notifications
Worker completions surface via `bin/dispatch-notify` (terminal-notifier + on-brand candy-brick icon; osascript fallback) and the `pdw` watch dashboard (`~/.local/bin/pdw`).
