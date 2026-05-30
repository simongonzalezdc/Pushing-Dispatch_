# Adaptive, Availability-Aware, Self-Healing Router — Design

Date: 2026-05-30
Status: Approved (design); pending implementation plan
Owner: Simon

## Problem

Pushing Dispatch routes purely on keyword + token-count heuristics and has **no
awareness of which executors are actually reachable**. Investigation found three
structural failures:

1. **Credential blindness.** Wrappers resolve keys via `ce_load_api_key()`
   (env → Keychain service `pushing-dispatch` → `pass` → `~/.codex/config.toml`).
   The user's keys actually live in `~/.zshrc` exports, `~/.config/goose/.env`,
   and the macOS Keychain service `dopamine-depot` (e.g. `dopamine-depot:gemini`,
   `dopamine-depot:minimax`). A dispatched worker runs in a non-interactive
   subprocess that never sources the shell, so those keys are invisible. Only
   OpenAI (Codex `auth.json`), Anthropic (Claude Code login), Kimi CLI, and
   Ollama are reachable at dispatch time.
2. **No availability awareness in routing.** `auto_route()` returns single
   hard-coded candidates per signal and will return an executor whose key is
   unreachable; the worker then dies at runtime with a generic exit code 4.
3. **No self-identification / no resilience.** Nothing learns which model is
   best per task, there is no per-account selection across the user's OpenAI
   logins, and a transient auth/rate-limit failure is not detected, isolated,
   re-routed, or recovered.

## Goals

- **Optimal, efficient, high-quality routing** under an *adaptive-balanced*
  objective: balanced cost/quality per task tier, automatic escalation to
  top-tier models for hard/deep/high-stakes work.
- **Availability-aware**: never route to an unreachable executor.
- **Self-healing**: detect runtime auth/rate-limit/network failures, isolate the
  bad lane, re-route automatically, and recover the lane when it returns.
- **Persistent**: credentials, availability/cooldown state, and outcome history
  survive across sessions and reboots.
- **Zero babysitting** (accessibility requirement): the system corrects itself
  without manual intervention; a single command surfaces health when asked.

## Non-Goals (this phase)

- Unbounded autonomous nesting (loop/cost risk). Cap at depth 2.
- Turning on the learning loop by default. Build the hook; enable deliberately
  once there is data.
- Swarm primitives (explicitly rolled back per project doctrine).

## Decisions (locked)

| Decision | Choice |
| --- | --- |
| Credential strategy | Consolidate all keys into Keychain service `pushing-dispatch` |
| Routing objective | Adaptive balanced (escalate for hard/deep work) |
| Intelligence | Availability-aware static matrix first; learning built but off |
| Nesting | Single availability-aware top router + nested dispatch depth 2 for breakout/architect seats |
| Learning | Outcome ledger + bias knob built now, disabled by default |

## Architecture

### 1. Credential layer — one source of truth

`bin/sync-credentials.sh` (idempotent, never prints secret values):

- Reads keys from current sources in priority order: existing
  `pushing-dispatch` Keychain entries → `~/.config/goose/.env` →
  `dopamine-depot:*` Keychain entries → interactive `~/.zshrc` (sourced in a
  subshell only to harvest names that are already exported there).
- Writes each into Keychain service `pushing-dispatch` under the account names
  the wrappers already expect: `kimi_api_key`, `moonshot_api_key`,
  `deepseek_api_key`, `minimax_api_key`, `custom_minimax_coding_plan_api_key`,
  `custom_inception_api_key`, `z_ai_api_key`, `kilo_api_key`, `gemini_api_key`.
- CLI-auth providers (OpenAI→Codex, Anthropic→Claude Code, local→Ollama) need no
  key; recorded as `cli-auth`.
- Re-runnable so rotated keys can be re-synced. Reports a per-provider
  found/missing table on completion (names only).

Keychain is the persistence substrate — survives reboot, available to
non-interactive subprocesses.

### 2. Availability resolver — `dispatch_lib/availability.py` (new)

For each executor in the matrix, determine reachability *without fetching secret
values into logs*:

- `provider = openai-codex` → `~/.codex/auth.json` present (and which accounts
  are available via `auth.<name>.json` files).
- `provider = anthropic` → Claude Code logged in.
- API-key providers → key resolvable via the same lookup order as
  `ce_load_api_key` (boolean presence check only).
- local (`ollama`, `lm-studio`) → CLI present / endpoint reachable.

Returns the set of available executors plus a per-executor reason. Result is
cached to `<dispatch_root>/availability.json` (default
`~/.local/share/pushing-dispatch/availability.json`) with a short TTL
(e.g. 300s) and an explicit `--refresh`. Written atomically (tmp + rename),
matching existing status-file convention.

### 3. Self-healing — cooldown/health ledger

- **Failure classification.** Extend the wrapper finalize path (currently maps
  every non-zero exit to code 4 "errored") to classify the error from the worker
  log/HTTP detail: `auth` (401 / expired token), `rate_limit` (429),
  `network`/timeout, or `task` (genuine task failure — *not* a lane fault).
- **Demotion.** On `auth`/`rate_limit`/`network`, write a cooldown entry for that
  executor to `<dispatch_root>/lane_health.json` (atomic) with an expiry
  timestamp (escalating backoff per failure class; rate_limit short, auth
  longer pending re-auth).
- **Re-route.** The router treats an executor in active cooldown as unavailable
  and falls to the next available candidate in the same tier — automatically,
  no user action.
- **Recovery.** Cooldown expiry, or a successful re-probe / successful dispatch,
  clears the demotion. `auth`-class failures also trigger a recovery attempt:
  for Codex, attempt token refresh; if unrecoverable, flag the provider as
  `needs-relogin` in the doctor output (the only case requiring a human, and it
  is surfaced rather than silently failing).
- **Credential drift healing.** If a key that was present goes missing, doctor
  detects the `pushing-dispatch` vs source mismatch and the sync script can
  re-pull. Optional periodic refresh via a SessionStart hook keeps Keychain
  current.

`task`-class failures are never treated as lane faults (failure is information,
per project doctrine — no auto-retry of the same work).

### 4. Router upgrade — `auto_route()` availability-aware + tiered

- Replace single-candidate signals with **ordered candidate lists per tier** in
  the matrix `[auto_route]` section, e.g.
  `hard_coding_task = ["codex-spark", "openai-gpt55-high", "zai-glm", "opus"]`.
- Complexity → tier mapping: trivial / standard / hard / deep / long-context /
  consult, derived from keywords + token estimate (+ optional explicit
  difficulty flag).
- The router walks the tier's candidate list and returns the first executor that
  is **mode-allowed AND available AND not in cooldown**. Adaptive-balanced:
  balanced default per tier, hard/deep tiers lead with top-tier models.
- `route --json` gains `available`, `considered`, `fallback_from`, `reason`.
- Back-compat: existing single-value `[auto_route]` keys still parse (treated as
  one-element lists) so nothing breaks mid-migration.

### 5. OpenAI multi-account selection

- OpenAI executors carry an optional `account` hint in the matrix.
- OpenAI wrappers call `codex-switch <account>` before exec. Because every
  dispatch is a fresh subprocess, per-dispatch switching takes effect (no
  mid-session restart problem).
- **Open item:** `~/.codex/ACCOUNTS.md` lists 2 accounts (iCloud, Puenteworks);
  user reports 3 (manifest references `CERAFICA`). Third account must be
  confirmed/added (`codex auth login` → save `auth.cerafica.json`) during
  implementation. Until then routing uses the 2 known accounts.

### 6. Self-identification layer — built, off by default

- Extend the append-only ledger (`budget.jsonl` pattern) into an **outcome
  ledger** recording per dispatch: executor, tier, success/failure class,
  duration, cost, and a quality signal (verifier/exit-status proxy initially).
- Add a `learning` knob to `[auto_route]`; when enabled, candidate ordering is
  biased by historical success/cost per tier. Disabled by default; flip on once
  data accumulates.

### 7. Nesting

- Keep `[nested_dispatch] max_depth`; raise target to **2** for breakout/architect
  seats only. Availability + cooldown filtering applies to child dispatches too.
  Self-dispatch remains denied. Budget cascade unchanged.

### 8. Observability — `pushing-dispatch doctor`

One command prints the live table: each executor's availability, auth source,
cooldown status, and any `needs-relogin` flags. Replaces guesswork when a lane
misbehaves. Extends (does not replace) `bin/check-prereqs.sh`.

## Data / State (all persistent)

| Artifact | Location | Lifetime |
| --- | --- | --- |
| Provider keys | Keychain service `pushing-dispatch` | Permanent (until rotated) |
| Availability cache | `<dispatch_root>/availability.json` | TTL (re-derived) |
| Lane health / cooldowns | `<dispatch_root>/lane_health.json` | Until expiry/recovery |
| Outcome ledger | `<dispatch_root>/outcomes.jsonl` | Append-only, permanent |

`<dispatch_root>` = `~/.local/share/pushing-dispatch`. All JSON written
atomically (tmp + rename); JSONL append-only.

## Error Handling

- Missing key at route time → executor unavailable → transparent fallback;
  doctor shows the gap.
- All candidates in a tier unavailable → fall through to the next-broader tier,
  finally to any mode-capable available executor; only if *nothing* is available
  does dispatch error (with an actionable message naming what to re-auth).
- Self-healing never silently swallows `task`-class failures — those surface as
  real worker failures (no auto-retry).

## Testing

- Unit: availability resolver (mock each provider's auth presence); router
  fallback ordering with executors marked down; cooldown demotion/expiry;
  failure classifier on sample logs (401/429/timeout/task).
- Integration: smoke test still passes; a forced-unavailable preferred executor
  re-routes to the next available; `route --json` shows `fallback_from`.
- Matrix back-compat: old single-value `[auto_route]` keys still validate.

## Rollout

1. Credential consolidation (`sync-credentials.sh`) + `doctor` — make state
   visible and reachable.
2. Availability resolver + router fallback (the core fix).
3. Self-healing cooldown/classification.
4. OpenAI account selection (after 3rd account confirmed).
5. Outcome ledger (off-by-default learning).
6. Nesting depth 2.

## Open Items

- Confirm/add the 3rd OpenAI account (`CERAFICA`).
- Quality signal definition for the outcome ledger (start with exit-status/
  verifier proxy; refine later).
