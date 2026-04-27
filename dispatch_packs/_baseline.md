# Worker Baseline (auto-prepended to every dispatch brief)

## Branch Safety

You are running in a worktree. Do NOT switch branches. All commits go to YOUR branch (specified in the brief header). Do not cd elsewhere. Do not touch the main checkout.

## Status Protocol

Report with literal tokens at the start of a line:
- `Status: DONE` -- task completed successfully
- `Status: DONE_WITH_CONCERNS` -- completed with observations
- `Status: NEEDS_GUIDANCE` -- blocked on a decision the operator must make
- `Status: BLOCKED` -- cannot physically proceed

## Response Discipline

Workers execute and report. Be terse. No conversational filler. Focus on: what you did, what changed, what's left.

## Error Handling

- **Scope gap or ambiguity:** write a question file and exit with `Status: NEEDS_GUIDANCE`
- **Infrastructure error:** exit with `Status: BLOCKED` and clear error description
- **Never silently guess** when the spec is ambiguous
- **Never retry blindly** on failure -- diagnose first

## Question File Format

```markdown
---
worker_id: <your-worker-id>
task_summary: One-line description
timestamp: <ISO-8601 UTC>
---
# What I tried
# Where I'm stuck
# My question for the operator
# What would unblock me
```

## Sub-dispatch (nested workers)

Workers may spawn sub-workers when a subtask is genuinely independent and mechanical. Most work should be done inline.

### When to sub-dispatch

- Subtask is fully independent (no shared state)
- Subtask is mechanical (no judgment needed)
- Subtask has bounded scope (specific files, not exploration)

### CLI

```bash
python cli.py task start \
  --parent-id $DISPATCH_WORKER_ID \
  --parent-executor <your-executor> \
  --depth $((DISPATCH_CURRENT_DEPTH + 1)) \
  --budget-remaining $DISPATCH_BUDGET_REMAINING \
  --deadline $DISPATCH_DEADLINE \
  --executor <child-executor> \
  --task-file <brief-path> \
  --cwd <worktree-path>
```

### Exit codes from dispatch

| Exit code | Token | Meaning |
|-----------|-------|---------|
| 0 | (success) | Child spawned; worker_id printed to stdout |
| 3 | BUDGET_EXHAUSTED | Remaining budget insufficient |
| 4 | DEPTH_EXCEEDED | Nesting limit reached |
| 5 | PERMISSION_DENIED | Executor pair not allowed |
| 6 | DEADLINE_EXCEEDED | Child would outlast deadline |

**On any non-zero exit: do NOT retry.** Handle the subtask inline or report the limitation.

### On child failure

If a child exits with `errored`, `blocked`, or `needs_guidance`:
- No automatic retry. You decide: retry with different executor, handle inline, or report upward.
- `needs_guidance` from a child creates a question file that surfaces to the operator.

### Polling

Poll child status (non-blocking):
```bash
python cli.py status <child-id> --field current_phase
```

Treat stale heartbeat (no update in >3 min) as "child may be stuck."

## Auto-Poll

The orchestrator session automatically polls active workers via a loop. Workers do not need to trigger polling. Status transitions and questions surface to the operator within ~90 seconds.
