---
description: Poll active dispatch workers for status transitions and questions
---

Run one polling cycle for active dispatch workers. This command is designed
to be called via `/loop 90s /dispatch-poll` from the orchestrator session.

## Steps

1. Check for active workers:
```bash
python3 cli.py list --active
```

2. Check for recently completed workers:
```bash
python3 cli.py completions
```

3. Check for pending questions from workers:
```bash
python3 cli.py questions
```

## Decision logic

- If **zero active workers**: respond with `LOOP_DONE` to terminate the polling loop. Clean up the session marker file.
- If **workers completed since last poll**: summarize the completions (worker ID, status, executor).
- If **questions pending**: surface the question content so the operator can respond.
- If **all workers still running**: report "N workers active, no transitions" (silent is healthy).

## Cleanup on loop termination

When all workers are done, remove the auto-poll marker:
```bash
rm -f "$DISPATCH_ROOT/auto_poll_active_${DISPATCH_SESSION_ID}"
```
