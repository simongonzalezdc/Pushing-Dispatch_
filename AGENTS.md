# ai-dispatch -- Agent Orientation

You are working in the `ai-dispatch` repo: a multi-model dispatch framework for AI coding agents.

## Architecture

Four pillars:
1. **Harness flip**: all AI providers route through one harness via Anthropic-compatible endpoints
2. **Brief-only context**: workers receive only baseline + declared packs + task body
3. **Matrix-driven routing**: `dispatch_matrix.toml` defines all executor capabilities
4. **Nested dispatch**: workers can spawn sub-workers with safety rails

## Key Paths

| Path | Purpose |
|------|---------|
| `cli.py` | Main CLI entry point |
| `breakout.py` | Worktree session manager |
| `dispatch_lib/` | Core library (routing, budget, permissions, status) |
| `bin/wrappers/` | Provider wrappers + shared `_exec.sh` |
| `dispatch_matrix.toml.example` | Reference executor configuration |
| `dispatch_packs/` | Context packs (baseline, detail packs, registry) |
| `docs/ORCHESTRATING.md` | Complete orchestrator guide |

## Rules

- Everything derives from the dispatch matrix. No hardcoded executor lists.
- No swarm code (rolled back, no provider support).
- No auto-retry on worker failure. Parent decides.
- Self-dispatch always denied (loop prevention).
- Brief assembly always prepends `_baseline.md`.

## Stack

- Python 3.11+ (stdlib only, tomllib for TOML)
- Bash 4+ for wrappers (set -euo pipefail)
- JSON status files (atomic writes)
- JSONL budget ledger (append-only)
- Conventional Commits for git messages
