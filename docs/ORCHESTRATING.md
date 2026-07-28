# Orchestrating with Pushing Dispatch

Pushing Dispatch is the model-selection front door. The orchestrator owns
judgment; Dispatch chooses an available executor from the active matrix.

## Normal Workflow

```bash
pushing-dispatch route --mode task --task "<brief>"
pushing-dispatch task start --executor auto --task "<brief>" --cwd "$PWD"
```

Use `breakout` for isolated multi-step implementation and `consult` for
read-only advice. Explicit executors are for a user-mandated harness or a
diagnostic probe, not preference-based routing.

## Current Routing Policy

| Need | Normal route |
|---|---|
| Atomic typo, one-file lint/format, or local rename | `ollama-xps-gpu`, accepted only after resident NUC validation |
| Unclassified ordinary work | `zai-glm`; resident Qwen and prepaid/cloud fallbacks follow |
| Explicit retry after unusable Luna result | `codex-terra` (high) |
| Exceptional final ladder | `codex-sol` (low, then medium, then high; stop) |
| Long context | `kimi-k3-cli` first through the Kimi subscription; `kimi-k3-ollama` next when Ollama Cloud exposes K3; then the availability-ranked fallback ladder |
| Retired Claude Opus-class work | `grok-build` (hard implementation, deep architecture, adversarial review, breakout, consult) |
| Visual work | Codex, Grok, Kimi K3 through either explicitly isolated lane, or AGY; never GLM |
| Gemini | AGY only |
| MiniMax M3 backup | GJC only |
| Free overflow | `kilo-free-auto` only |
| Bounded local coding (m3-class, tools + proof) | **`unsloth-nucbox`** (Ornith sticky on `:8890`); then cloud fallbacks |
| Bounded general/review dual-load workcells | Retired while Ornith is resident (`qwen35-*` / `qwen36-35b-coding` need `:8892`) |

GLM 5.2 runs through the Claude Code harness and has no vision. If any lane's
native search fails or is unreliable, use the global DuckDuckGo `ddg` MCP.

### Cloud orchestrator → Ornith leaf (every cloud model)

**Owning YES/NO card (do not fork):** fleet  
`launchpad/docs/agents/ORNITH-GUIDELINES.md` § *Cloud-orchestrator card*.  
Pack: `includes: ornith-leaf` · ops: `ops/unsloth-nucbox/README.md`.

| Dispatch **YES** | Dispatch **NO** (use cloud) |
|------------------|-----------------------------|
| Bounded local coding/ops + proof | Architect / ralplan |
| RED→GREEN tests, one-file patches | Independent critic / PR review |
| Mechanical local sweeps | Security / auth / migrations |
| Sliced m3 leaf from a campaign | Vision / web / long-context / breakout-top |
| | Typos → `kilo-free-auto` |

**m3 discriminator (all required):** bounded · localized · reversible · verifying.

```bash
# 1) Prefer auto (local-coding keywords → unsloth-nucbox when available)
pushing-dispatch route --mode task --task "local coding: <one-sentence goal + acceptance>"

# 2) Explicit leaf
pushing-dispatch task start \
  --executor unsloth-nucbox \
  --cwd "$PWD" \
  --task "$(cat <<'EOF'
# Task
<bounded one-file or small-module change>

# Constraints
- Stay inside the named paths.
- Prefer skill: systematic-debugging | test-driven-development | verification-before-completion when matching.
- Run the focused test/check and report command + result.
- End with Status: DONE (or DONE_WITH_CONCERNS / NEEDS_GUIDANCE / BLOCKED).

# Acceptance
<falsifiable check>
EOF
)"
```

**Ops:** **serialize** Ornith leaves (one at a time; GPU `parallel=1`). Progressive
skills (obra + Matt) load by catalog then `read`. Health:
`ssh nucbox '~/unsloth-ops/bin/ornith-workhorse-verify.sh'` (expect `fail=0`).

The auto-router admits only deterministic, bounded task families to local
specialist tiers. Broad, risky, repository-wide, long-context, visual, breakout,
and consult work keeps its stronger existing tier. Ornith (`unsloth-nucbox`) is
the sticky resident workhorse (32,768 context, 16,000 routing ceiling for coding).
On-demand dual-load workcells on `:8892` remain defined but unavailable while
Ornith is sticky. The unused headroom covers baseline, progressive skill catalog,
instructions, and output; never substitute advertised training context.

## Briefs

A brief is the worker contract. Keep it bounded and explicit:

```markdown
---
title: Fix authentication race
includes:
  - branch-safety
---

# Task

Fix the duplicate-session race in `src/auth/login.py`.

# Constraints

- Modify only the handler and its test.
- Use the existing lock abstraction.
- Run the focused test and report the command/result.
```

Omit `executor` to let Dispatch route. `includes:` must begin at column zero
and name a registered pack.

## Nested Dispatch

Nested workers require both a depth allowance and an explicit current
parent/child permission in `dispatch_matrix.toml`:

```yaml
nested_dispatch:
  max_depth: 1
  allowed_executors: [codex-luna, kilo-free-auto]
```

Self-dispatch and leaf-parent dispatch are denied. Keep parallel slices
independent and use separate worktrees for overlapping repositories.

## Monitoring and Recovery

```bash
pushing-dispatch list --active
pushing-dispatch status <worker-id>
pushing-dispatch questions
pushing-dispatch completions
pushing-dispatch doctor
```

On `DONE`, review the diff and verification evidence. On `NEEDS_GUIDANCE`,
answer the question file. On a real stall, inspect the log, stop the worker,
and re-dispatch with `auto` so availability/cooldown routing can choose a healthy
lane.

## Green Gate

Before declaring the fleet healthy:

```bash
python3 -m pytest -q
pushing-dispatch validate-matrix dispatch_matrix.toml
pushing-dispatch doctor --probe
```

All eleven active wrappers must pass the live probe.
