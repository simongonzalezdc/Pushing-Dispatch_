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
| Long context (>50K tokens) | `kimi-k27` | Native Kimi K2.7 lane |
| Mechanical refactor | `codex-luna` | Fast subscription lane |
| Everyday work | `codex-terra` | Default quality/cost balance |
| Hard coding or synthesis | `codex-sol` | Frontier hard/consult lane |
| Visual work | Terra/Sol, Kimi, or AGY | GLM has no vision |
| Free overflow | `kilo-free-auto` | Kilo free models only |

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
