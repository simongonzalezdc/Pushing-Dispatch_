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
| Typo, lint, tiny mechanical edit | `codex-luna` |
| Ordinary implementation | `codex-terra` |
| Hard implementation, architecture, consult | `codex-sol` |
| Long context | `kimi-k27` |
| Visual work | Codex, Kimi, or AGY; never GLM |
| Gemini | AGY only |
| MiniMax M3 backup | GJC only |
| Free overflow | `kilo-free-auto` only |
| Local/private | `lm-studio` |

GLM 5.2 runs through the Claude Code harness and has no vision. If any lane's
native search fails or is unreliable, use the global DuckDuckGo `ddg` MCP.

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

All ten active wrappers must pass the live probe.
