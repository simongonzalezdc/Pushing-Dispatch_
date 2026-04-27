# Pushing Dispatch_ -- Claude Code Orientation

You are working in the `pushing-dispatch` repo: a multi-model dispatch framework for AI coding agents.

## What This Is

A system that lets an orchestrator model dispatch worker agents across multiple providers (Anthropic, Moonshot/Kimi, DeepSeek, and others) through a unified CLI. Four pillars:

1. **Harness flip**: all providers route through one Claude Code harness via Anthropic-compat endpoints
2. **Brief-only context**: workers see only baseline + declared packs + task (no ambient context leakage)
3. **Matrix-driven routing**: `dispatch_matrix.toml` is the single source of truth for executor capabilities
4. **Nested dispatch**: workers can spawn sub-workers with budget cascade, permissions, depth caps

## Key Files

- `cli.py` -- main CLI (`task start`, `breakout start`, `list`, `status`, `kill`, `budget`)
- `breakout.py` -- worktree session manager
- `dispatch_lib/` -- core library (routing, budget, permissions, status, tree ops)
- `bin/wrappers/` -- provider shell wrappers (each ~20 lines + shared `_exec.sh`)
- `dispatch_matrix.toml.example` -- reference executor matrix
- `dispatch_packs/` -- context packs for brief assembly
- `hooks/` -- auto-poll hook for Claude Code sessions
- `docs/ORCHESTRATING.md` -- the orchestrator runbook

## What NOT To Do

- Do not hardcode executor lists. Everything derives from the matrix.
- Do not add swarm code. Phase 4 was rolled back (no provider supports the required primitives).
- Do not auto-retry failed workers. Failure is information, not a trigger for retry.
- Do not allow self-dispatch in the permissions matrix (loop risk).
- Do not remove the `_baseline.md` prepend from brief assembly (it carries branch safety and status protocol).

## Conventions

- Python 3.11+, no external dependencies beyond stdlib + tomllib
- Shell scripts use `set -euo pipefail`
- Status files are JSON, written atomically (tmp + rename)
- Budget ledger is append-only JSONL
- Commit messages follow Conventional Commits

## Detail Packs

For deep context on specific topics, read the relevant pack in `dispatch_packs/`:
- `dispatch-protocol.md` -- matrix, modes, routing, budget
- `branch-safety.md` -- worktree rules
- `brief-format.md` -- brief schema and includes: protocol
- `nested-dispatch.md` -- permissions, budget cascade, depth caps
- `orchestrator-protocol.md` -- how the orchestrator should use the system
