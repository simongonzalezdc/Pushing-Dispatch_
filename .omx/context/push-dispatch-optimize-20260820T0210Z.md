# Context: push-dispatch optimize (utilization + naming + notifications)

task_statement: Optimize utilization of pushing-dispatch features and align dispatch_matrix.toml + runtime state with the owner's real setup and way of working; add cute human-readable executor names with color + emojis; give dispatch notifications a cuter custom icon.

desired_outcome: (1) config reflects actual usage (routing tiers, budgets, cooldowns, learning); (2) every executor shows a readable name with emoji + color in CLI + pdw; (3) completion notifications use an on-brand custom icon; (4) consensus-verified plan + durable handoff.

known_facts (gathered 2026-08-20):
- outcomes.jsonl: 3,857 records. Workhorse = zai-glm (2,232 success; 16 rate_limit). codex-terra 156, grok-build 117 success + 139 task, unsloth-nucbox 83 success + 135 task, codex-luna 103, codex-sol 101, kimi-coding 47, minimax-m3 37, dsh 33, agy-gemini-flash 18. Retired lanes still present in outcomes (openai-mini, codex-spark, haiku, gemini-flash, agy-gemini-pro) — history only.
- availability.json: `executors: {}` — EMPTY cache (only ts). Routing currently has no availability snapshot (doctor --probe needed; TTL to verify).
- lane_health.json: stale cooldowns for retired executors (openai-gpt55, codex-spark, haiku, opus, minimax, kimi-code) + current lanes (kimi-k3-cli/key/kyanite auth until ~2026-08-20, grok-build rate_limit expired, agy-gemini-flash rate_limit).
- dispatch_matrix.toml: 21 executors, schema_version=1, [auto_route] 10 tier lists + learning=false, [nested_dispatch] max_depth=2 + permissions map. No display_name/emoji/color fields.
- matrix_validator: REQUIRED_EXECUTOR_FIELDS enforced; unknown extra fields not rejected → adding optional display_name/emoji/color is safe.
- cli.py name render points: list (line ~373), route output (line ~540), doctor table, status.
- terminal-notifier installed at /opt/homebrew/bin/terminal-notifier (supports -appIcon png).
- pdw (~/.local/bin/pdw) is the owner's new watch command; its notify() currently uses osascript (no icon). pdw purged 57 dead-zombie status files this session; status_writer.py has no GC.
- kimi-k3-kyanite in auth cooldown (needs re-login) — matches earlier failed lane.
- GLOBAL_AGENT_ROUTING.md policy: all coding agents route through dispatch; doctor is the health surface.

constraints:
- Planning mode: no code edits to dispatch during ralplan (artifacts only in this .omx).
- Keep current lanes working: zai-glm first for standard, grok-build for hard/breakout, unsloth for local, kilo-free for overflow.
- Never weaken: availability+cooldown routing authority, self-healing, never-stage (repo is canonical Forgejo simon/pushing-dispatch — changes land via owner).
- Naming must be safe in ANSI output (no raw escape in files; color via terminal render).

unknowns:
- Whether learning=true re-biasing is desirable with 3,857 records skewed by zai-glm (skew risk).
- Icon style the owner wants (candy brick? robot? spark?) — default on-brand glass candy brick.
- Whether to enable DISPATCH_NESTED for closeout-style multi-lane campaigns.

likely_touchpoints: dispatch_matrix.toml, cli.py (list/status/doctor/route), dispatch_lib/matrix_validator.py (+tests), bin/wrappers/_exec.sh (no change), ~/.local/bin/pdw, ~/.local/share/pushing-dispatch/availability.json + lane_health.json (runtime state), assets/dispatch-icon.png, GLOBAL_AGENT_ROUTING.md note.

gates: consensus gate complete only after Architect + Critic approve in order; handoff must not start edits without owner approval of lane choice.
