# Orchestrator Protocol

This pack is for the orchestrator model (the main session). It describes how to use the dispatch system effectively.

## When to Dispatch

Dispatch when a task:
- Would consume >15 minutes of focused execution
- Requires reading more than ~5 files
- Involves a different branch or worktree
- Is mechanical enough that a cheaper executor can handle it
- Can run independently while you continue other work

Stay inline when:
- The task is a single-file edit
- You need the result immediately for a decision
- The task requires conversational back-and-forth with the user

## Choosing an Executor

| Signal | Executor | Why |
|--------|----------|-----|
| Bounded local coding / small verify loop | **`unsloth-nucbox`** (Ornith) | Free sticky NUC leaf; progressive obra+Matt skills; m3-class only |
| Long context (>50K tokens) | Matrix-ranked candidates | `kimi-k3-cli` first through the Kimi subscription; isolated `kimi-k3-ollama` next when Ollama exposes it |
| Mechanical refactor | `codex-luna` | Fast subscription lane |
| First attempt for ordinary work | `codex-luna` / `zai-glm` via `auto` | Route, don't hand-pick |
| Unusable Luna result | `codex-terra` | Explicit retry at high; do not call `auto` again |
| Genuinely frontier fallback | `codex-sol` | Explicit low → medium → high ladder; stop after high |
| Retired Claude Opus-class work | `grok-build` | Hard implementation, deep architecture, adversarial review, breakout, consult |
| Visual work | Codex, Grok, Kimi, or AGY | GLM has no vision |
| Free overflow | `kilo-free-auto` | Kilo free models only |

### Ornith one-liner (local leaf)

**Canon YES/NO:** fleet `launchpad/docs/agents/ORNITH-GUIDELINES.md` § Cloud-orchestrator card. Pack: `includes: ornith-leaf`.

```bash
pushing-dispatch route --mode task --task "local coding: <bounded goal + acceptance>"
pushing-dispatch task start --executor unsloth-nucbox --cwd "$PWD" \
  --task "local coding: <bounded goal + acceptance>. Status: DONE"
```

| YES | NO |
|-----|----|
| Bounded local coding/ops + proof | Architect / critic / security / vision / web sole |
| RED→GREEN tests, one-file patches | Breakout-top, multi-module hard, long-context |
| Sliced m3 leaf from cloud campaign | Free typos (`kilo-free-auto`), chat Q&A |

**Serialize** Ornith jobs (one leaf at a time). See `docs/ORCHESTRATING.md` § Cloud orchestrator → Ornith leaf.

## Writing a Brief

1. Be specific about the task. Name files, functions, expected outcomes.
2. Use `includes:` for shared context rather than pasting large blocks.
3. Set constraints explicitly: what the worker should NOT do.
4. For worktree work, use `breakout` mode with a descriptive slug.

## Handling Worker Results

- Poll status via `cli.py status <worker-id>` or rely on auto-poll.
- On `DONE`: review the diff, merge if satisfied.
- On `DONE_WITH_CONCERNS`: read the concerns, decide if they matter.
- On `NEEDS_GUIDANCE`: read the question file, answer via `cli.py answer`.
- On `BLOCKED`: diagnose and either fix the blocker or reassign.
- On stall: check logs, consider killing and re-dispatching.

## Parallel Dispatch

You can dispatch multiple workers simultaneously. Each runs in its own worktree. Use `list --tree` to see all active work.

When dispatching parallel workers:
- Ensure tasks are truly independent (no shared mutable state)
- Use different worktree slugs
- Monitor aggregate budget with `budget --tree`

## Nested Dispatch

When writing a brief that should allow the worker to sub-dispatch, add:

```yaml
nested_dispatch:
  max_depth: 2
  allowed_executors: [codex-luna, kilo-free-auto]
```

This injects the nested dispatch feature flag and depth cap at launch time.
