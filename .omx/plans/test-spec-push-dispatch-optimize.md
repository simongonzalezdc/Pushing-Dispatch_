# Test spec — push-dispatch optimize (v2, Architect-amended)

## Phase 1 — display names
- [ ] `validate-matrix` passes with display_name + color on all 21 executors
- [ ] NEGATIVE: validator rejects empty display_name; rejects color not in {red,orange,yellow,green,blue,magenta,cyan,white} (A3)
- [ ] `dispatch_matrix.toml.example` + header optional-field comment synced with the matrix (A7)
- [ ] `list` on TTY shows emoji names; piped output has NO ANSI; mode/phase columns stay aligned with a display-name row (A4)
- [ ] MACHINE CONTRACT: `route` plain output = raw executor key (always); `route --json` adds `executor_display` (A2)
- [ ] MACHINE CONTRACT: `status` JSON + `--field executor` = raw key (A2)
- [ ] doctor table + `completions` render display names
- [ ] pdw dashboard rows + notify lines use matrix display_name/color; pdw --json/--zombies stay raw (A5)
- [ ] `python3 -m pytest -q` green (validator + render + alignment tests)

## Phase 2 — runtime/config (diagnosis-first)
- [ ] `resolve()` never writes an empty availability dict (guard test) (A1)
- [ ] behavior test: write empty cache → run a route → cache refilled (documents self-heal; passes today)
- [ ] `doctor --probe` → availability.json `executors` non-empty
- [ ] recompute latency measured once (C1b) — TTL raised only if measured pain
- [ ] lane_health GC: retired keys incl. openai-gpt55-high/xhigh pruned; auth-class entries for matrix-live lanes (kimi-k3-kyanite) preserved (A9)
- [ ] learning (per G2): dry-run snapshot of re-biased order before enabling
- [ ] nested (per G3): DISPATCH_NESTED=1 works at max_depth=2; cwd-lock discipline documented
- [ ] C4 tier edits grounded in a live doctor snapshot (local lanes currently unavailable — no blind reorder) (A8)
- [ ] no routing regression: standard tier still resolves zai-glm first when available

## Phase 3 — notifications
- [ ] `bin/dispatch-notify` fires terminal-notifier with -appIcon + -sound; icon resolves via script dir, NOT CWD (A6)
- [ ] fallback: terminal-notifier absent → osascript (no crash)
- [ ] a real cheap worker completion shows the icon notification (visual check, Light + Dark)
- [ ] pdw --notify / --loop route through dispatch-notify

## Phase 4 — land (split gate)
- [ ] repo-side commit series (matrix, cli.py, validator, dispatch-notify, assets, example) via owner's Forgejo path
- [ ] owner-local pdw replacement (`~/.local/bin/pdw`) verified against the same gates
- [ ] full green gate: pytest + validate-matrix + doctor --probe + icon notification fired

## Out of scope
Routing authority, cooldown semantics, budgets, wrapper invocation — untouched.
