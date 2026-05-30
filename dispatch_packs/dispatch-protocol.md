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
2. The brief's tier, derived from token count + keyword signals + mode
3. The tier's ordered candidate list in `[auto_route]`
4. **Availability + cooldown filtering** — the router walks the candidate list
   and returns the first executor that is mode-allowed, reachable right now, and
   not in a self-healing cooldown. It never returns a dead lane.

Tiers and their `*_candidates` lists (matrix-driven, ordered best-first):
- `long_context_candidates` — >50K tokens or "summarize the entire …"
- `consult_candidates` — explicit consult mode (advisory/review)
- `hard_task_candidates` / `hard_breakout_candidates` — implement/debug/architect
- `trivial_candidates` — small mechanical work
- `standard_candidates` — everything else

Availability is computed per provider (CLI login for OpenAI/Anthropic, key
presence for API providers, local CLI for ollama/lm-studio) and cached with a
short TTL. Single-value back-compat keys still parse if a list is absent.

### Self-healing

A worker that fails with auth / rate-limit / network errors demotes its lane
into a cooldown (`lane_health.json`); the router reroutes around it and the lane
recovers on cooldown expiry or the next success. Genuine task failures do not
demote a lane. `pushing-dispatch doctor` shows the live availability/cooldown
table; `bin/sync-credentials.sh` consolidates provider keys into the
`pushing-dispatch` Keychain service.

## Budget Tracking

Every worker's cost is logged to an append-only JSONL ledger. The `budget` subcommand shows today's spend, optionally grouped by tree (for nested dispatch).

Metered providers (Moonshot, DeepSeek) have real per-token costs. Subscription providers (Anthropic) track token counts for visibility but cost shows as $0.00.

## Stall Detection

Each executor has a `stall_threshold_seconds` in the matrix. If a worker produces no output for this duration, it is flagged as stalled. The auto-poll mechanism surfaces stalls to the operator.
