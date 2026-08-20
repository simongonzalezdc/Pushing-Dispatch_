# PRD — push-dispatch optimize: utilization + readable names + cute notifications (v2, Architect-amended)

Status: REVISED (Planner, after Architect ITERATE A1–A9) · Slug: push-dispatch-optimize · Date: 2026-08-20 · Repo: ~/.local/share/pushing-dispatch/repo

## 1. Purpose
Align pushing-dispatch with the owner's real usage and way of working; make executors readable (emoji + color) at human surfaces; make notifications cute (custom icon). Consensus plan; execution via explicit lane after approval.

## 2. Scope
IN: matrix display fields + rendering at human surfaces; availability-cache diagnosis + guard; stale-cooldown GC; learning + nested flags per rulings; icon + dispatch-notify helper; validation + tests. OUT (owner rulings): G1 icon style, G2 learning, G3 nested.

## 3. Phases

### Phase 0 — Owner gates
- G1 Icon art style (default: candy polycarbonate brick in the glass identity, with a dark outline so it reads on both Light and Dark notification chrome; pastel-only washes out on dark mode).
- G2 `learning = true` (accept zai-glm outcome skew) or keep off with snapshot dry-run first.
- G3 DISPATCH_NESTED on (max_depth=2, cwd-lock discipline documented) or off.

### Phase 1 — Matrix display names (emoji + color)
- N1 Add optional fields to all 21 executors: `display_name` + `color`. Color enum extended to {red, orange, yellow, green, blue, magenta, cyan, white}. Palette (as planned, with `orange` for Terra; `🟤` Ornith + `🩵` Kilo Free documented as deliberate emoji-with-mismatched-color in a matrix comment). Sync `dispatch_matrix.toml.example` + the header comment's optional-field list (A7).
- N2 Render display names ONLY at human surfaces: `list`, `doctor` table, `completions`, pdw dashboard rows, notify lines. **Machine surfaces stay raw (A2):** `route` plain output keeps the raw executor key (cli.py:545); add `executor_display` to `route --json` payload only; `status` keeps raw JSON + `--field` semantics (optional `--human` summary block, out of scope v1).
- N3 pdw: read matrix display_name/color (tomllib) for dashboard + notify lines; `--json`/`--zombies`/`--purge` stay raw (A5).
- N4 matrix_validator: optional display_name non-empty + color in enum; NEGATIVE tests for both (A3).
- N5 cmd_list width: widen the executor column (~22) or pad on name-only so emoji (double-width) doesn't misalign mode/phase; alignment test (A4).

### Phase 2 — Runtime/config (diagnosis-first, A1)
- C1 Availability cache — REWRITE around diagnosis: (a) root-cause `executors: {}` — `resolve()` only writes after iterating matrix executors, so `{}` implies an empty matrix passed in; add a guard in `resolve()` that never writes an empty dict (warn instead) — the only code change (A1); (b) measure one full recompute (doctor rows); raise `CACHE_TTL_SECONDS` (currently 300) ONLY if recompute latency is the measured pain — keep 300s otherwise for ollama-cloud dynamic auth; (c) no inline `task start` probe guard — the choke point is `available_set()`/`auto_route`, and only if the guard is actually needed (self-heal already covers it).
- C2 lane_health GC keyed on matrix membership — prunes retired keys incl. `openai-gpt55-high`/`openai-gpt55-xhigh` (A9); never prune auth-class entries for matrix-live lanes (kimi-k3-kyanite relogin visibility stays even after `until` passes); optionally sweep expired entries.
- C3 learning per G2; if on, snapshot dry-run of re-biased candidate order against outcomes.jsonl (3,857 records) before enabling.
- C4 Candidate lists sanity-check grounded in a LIVE `doctor` snapshot (A8): all 6 local lanes currently `available:false` — reorder local tiers only with fresh evidence, not the stale assumption.
- C5 Nested per G3; cwd-lock discipline (one mutator per worktree) documented in dispatch_packs/nested-dispatch.md.
- C6 Tracking layer: wire hooks/auto_poll.sh into the owner's Claude Code settings; pdw remains the watch surface; optional status_writer GC (dead-pid stale files) flagged to owner.

### Phase 3 — Cute notifications
- I1 Generate icon PNG per G1 → `assets/dispatch-icon.png` (dark-outline candy brick, Light+Dark safe).
- I2 `bin/dispatch-notify`: `terminal-notifier -appIcon <icon> -sound default`; icon path resolved RELATIVE TO THE SCRIPT (repo checkout), not CWD (A6); graceful osascript fallback.
- I3 pdw notify() → dispatch-notify (loop + notify).
- I4 One-line GLOBAL_AGENT_ROUTING.md note.

### Phase 4 — Verification + land (split gate, A5)
- Repo-side commit series (matrix, cli.py, validator, dispatch-notify, assets, example sync) → owner's Forgejo land path.
- Owner-local pdw replacement (`~/.local/bin/pdw`) landed separately, verified against the same gates.
- Full green gate: pytest + validate-matrix + doctor --probe + a real cheap worker (kilo-free/ollama) firing the icon notification.

## 4. Success criteria
1. All 21 executors have display_name + color; validator enforces (incl. negative tests); example + header synced.
2. Human surfaces render emoji names on TTY (no ANSI in files/pipe); **route plain + status JSON remain raw keys** (machine contract intact).
3. `resolve()` never writes an empty availability dict; cache self-heal behavior documented by a behavior test (A1).
4. lane_health contains only matrix-live executors (auth-class for live lanes preserved).
5. learning + nested match owner rulings; documented.
6. Notifications show the custom icon + sound via dispatch-notify; fallback safe.
7. Tests green; routing authority untouched.

## 5. RALPLAN-DR (short mode)
PRINCIPLES: 1 Config reflects real usage (matrix = source of truth; runtime state never silently drifts). 2 Readable at human surfaces, raw at machine surfaces. 3 Non-breaking — routing/cooldown authority untouched. 4 Land through the owner; split repo vs owner-local artifacts. 5 Cute on purpose (names + icon reduce misreads at a glance).

DECISION DRIVERS: 1 zai-glm = 2,232/3,857 — keep it first for standard, never misroute. 2 Diagnose before fixing (empty cache is self-healing; the plan doesn't invent repairs). 3 Owner asked for names + icon — the visible payoff, shipped with the config fixes.

VIABLE OPTIONS: A — Matrix fields + human-surface rendering + notifier + diagnosis-first config fixes (this plan). B — Config-only (misses the asks). INVALIDATED. C — Full display-layer refactor (overkill, touches machine contracts). INVALIDATED. Recommend A.

## 6. Architect amendments folded
A1 C1 diagnosis-first + resolve() never-writes-empty guard · A2 machine surfaces raw (route plain, status JSON; --json + executor_display) · A3 color enum + orange + negative validator tests · A4 list width/emoji alignment + test · A5 split land gate (repo vs ~/.local/bin/pdw) · A6 dispatch-notify icon path via script dir · A7 matrix example + header sync · A8 C4 grounded in live doctor snapshot · A9 GC covers gpt55-high/xhigh, never prunes live auth-class.

## 7. Follow-ups
G1/G2/G3 rulings. Availability recompute latency measurement (C1b). status_writer GC optional add (owner interest).
