# Pushing Dispatch_ -- Agent Orientation

You are working in the `pushing-dispatch` repo: a multi-model dispatch framework for AI coding agents.

## Architecture

Four pillars:
1. **Harness flip**: providers use their supported agentic harness; Claude Code defaults to Z.AI GLM 5.2
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
- Anthropic subscription executors are retired; do not restore Opus/Sonnet/Haiku lanes.
- `zai-glm` is GLM 5.2. GJC provides explicit GLM 5.2 and MiniMax M3 backup paths.
- GLM has no vision capability. Visual tasks must route to a matrix-declared `vision` executor, never GLM.
- If any model's normal search path fails or produces unusable results, use the global DuckDuckGo `ddg` MCP fallback; never invent search results or citations.
- Kimi K2.7 is the single `kimi-k27` lane, exclusively through native `kimi-cli` using its managed `kimi-for-coding` alias; never Claude Code or GJC.
- Gemini is exclusive to AGY; do not route Gemini through Gemini CLI or the legacy direct API wrappers.
- Codex uses the ChatGPT subscription exclusively: Luna for trivial work, Terra as the everyday default, and Sol for hard/consult work. GPT-5.5, Codex OSS, and NUCBox Gemma are retired.
- Kilo uses the native Kilo CLI and only `kilo/kilo-auto/free`. Rotating `:free` monthly models require live catalog verification before temporary use; paid Kilo models are forbidden.
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
