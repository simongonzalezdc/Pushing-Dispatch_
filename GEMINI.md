# Pushing Dispatch_ -- Gemini CLI Orientation

You are working in the `pushing-dispatch` repo: a multi-model dispatch framework for AI coding agents.

## Architecture

Four pillars:
1. **Harness flip**: all AI providers route through one harness via Anthropic-compatible endpoints
2. **Brief-only context**: workers receive only baseline + declared packs + task body
3. **Matrix-driven routing**: `dispatch_matrix.toml` defines all executor capabilities
4. **Nested dispatch**: workers can spawn sub-workers with safety rails

## Tool Mapping (Gemini CLI equivalents)

| Claude Code Tool | Gemini CLI Equivalent |
|-----------------|----------------------|
| Read | read_file |
| Write | write_file |
| Edit | edit_file |
| Bash | run_command |
| Glob | list_files |
| Grep | search_files |

## Key Paths

| Path | Purpose |
|------|---------|
| `cli.py` | Main CLI entry point |
| `breakout.py` | Worktree session manager |
| `dispatch_lib/` | Core library |
| `bin/wrappers/` | Provider wrappers + shared `_exec.sh` |
| `dispatch_matrix.toml.example` | Reference executor config |
| `dispatch_packs/` | Context packs for brief assembly |
| `docs/ORCHESTRATING.md` | Complete orchestrator guide |

## Rules

- Everything derives from the dispatch matrix. No hardcoded executor lists.
- No swarm code (rolled back).
- No auto-retry on worker failure.
- Self-dispatch always denied.
- Brief assembly always prepends `_baseline.md`.

## Stack

Python 3.11+, Bash 4+, JSON status files, JSONL budget ledger, Conventional Commits.
