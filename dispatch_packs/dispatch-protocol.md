# Dispatch Protocol

## The Matrix

`dispatch_matrix.toml` is the single source of truth for:
- Which executors exist and what wrapper each uses
- Which modes each executor supports (task, breakout, consult)
- Thinking token defaults and hard ceilings
- Context window sizes
- Stall detection thresholds
- Nested dispatch permissions

The CLI reads the matrix at startup. No hardcoded executor lists.

## Modes

- **task**: Short-lived, focused work. Worker runs to completion and exits. Most dispatches are tasks.
- **breakout**: Long-running, worktree-isolated work. Gets its own git branch. Used for multi-step implementations.
- **consult**: Read-only advisory. Worker cannot modify files. Used for code review, architecture advice.

## Executor Selection

The auto-router picks an executor based on:
1. Explicit `executor:` field in the brief (always honored)
2. Token count of the assembled brief
3. Keyword signals in the brief body
4. Mode-specific defaults from the matrix

Heuristics:
- Long-context (>50K tokens): prefer Kimi (256K window)
- Mechanical/trivial: prefer Haiku (fast, cheap)
- Hard coding with strong spec: try DeepSeek or Kimi-think
- Synthesis/planning/orchestration: prefer Opus
- Default: Sonnet

## Budget Tracking

Every worker's cost is logged to an append-only JSONL ledger. The `budget` subcommand shows today's spend, optionally grouped by tree (for nested dispatch).

Metered providers (Moonshot, DeepSeek) have real per-token costs. Subscription providers (Anthropic) track token counts for visibility but cost shows as $0.00.

## Stall Detection

Each executor has a `stall_threshold_seconds` in the matrix. If a worker produces no output for this duration, it is flagged as stalled. The auto-poll mechanism surfaces stalls to the operator.
