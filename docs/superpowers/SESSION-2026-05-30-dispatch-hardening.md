# Session Record — Dispatch Hardening (2026-05-30)

Branch: `feat/adaptive-self-healing-router` (local only — remote
`PUSHINGSQUARES/Pushing-Dispatch_` is not owned by this user; not pushed).

## What this session delivered

### 1. Adaptive, availability-aware, self-healing router (12-task plan)
Design spec + plan: `docs/superpowers/specs/2026-05-30-adaptive-router-design.md`,
`docs/superpowers/plans/2026-05-30-adaptive-self-healing-router.md`.

- `dispatch_lib/availability.py` — resolves which executors are reachable *now*
  (CLI login for OpenAI/Anthropic, key presence for API providers, local CLI for
  ollama/lm-studio/codex-oss). TTL cache; self-heals on matrix drift; never reads
  secret values. Anthropic detected via the `Claude Code-credentials` Keychain
  service. API-key presence also checks the `~/.codex/config.toml` fallback
  (where the GLM/`Z_AI_API_KEY` lives).
- `dispatch_lib/lane_health.py` — failure classifier (auth/rate_limit/network/
  task) + persisted cooldown ledger (`lane_health.json`). task-class failures
  never demote a lane.
- `dispatch_lib/outcomes.py` — append-only outcome ledger (`outcomes.jsonl`);
  substrate for the off-by-default learning loop.
- `dispatch_lib/auto_router.py` — rewritten: brief → tier → ordered candidate
  list → first executor that is mode-allowed AND available AND not in cooldown.
  Raises `NoExecutorAvailable` instead of returning a dead lane. consult mode is
  authoritative over coding-keyword heuristics. Back-compat single-value keys.
- `dispatch_matrix.toml(.example)` — ordered `*_candidates` per tier,
  `key_env`/`key_account` on every API-key executor, OpenAI `account` hints,
  `learning=false`, nesting `max_depth=2`.
- `cli.py` — `doctor` command (live availability/cooldown/relogin table),
  enriched `route --json` (tier/considered/fallback_from/available), launch path
  exports `CE_EXECUTOR_NAME`/`CE_TIER`/`CE_OPENAI_ACCOUNT`.
- `bin/wrappers/_exec.sh` — self-healing centralized in `ce_finalize_status`:
  done → recover + record success; errored → classify log, demote, record;
  needs_guidance/blocked → record task (no demote).
- `bin/wrappers/codex.sh` — per-dispatch OpenAI account switch via `codex-switch`.
- `bin/sync-credentials.sh` — consolidates provider keys into the
  `pushing-dispatch` Keychain service.
- `hooks/auto_poll.sh` — warms the availability cache once per session (TTL-guarded).
- Tests: `tests/` (28 stdlib `unittest` tests, all passing). Run:
  `python3 -m unittest discover -s tests`.

### 2. International Coding Plan endpoints — verified/corrected
- GLM (Z.ai): `https://api.z.ai/api/anthropic` ✓
- Kimi: `https://api.kimi.com/coding` ✓
- MiniMax: `https://api.minimax.io/anthropic` ✓ — **fixed** `minimax-m25.sh`
  which pointed at the China endpoint `api.minimaxi.com`.

### 3. Provider wrappers + setup scripts committed
The full wrapper set the matrix references (codex-*, gemini-*, kilo-*, minimax-*,
zai*, kimi-coding, moonshot, deepseek, lm-studio, inception, haiku/opus/sonnet),
plus `bin/install-global-routing.sh`, `MANIFEST_REPLACEMENT_PROVIDERS.md`, and
`PI_CODEX_CLAUDE_SETUP.md`. `.gitignore` now excludes `.omc/` (runtime state).

## Out-of-repo machine config changed this session (NOT in this repo)

These are personal dotfiles — saved on disk, documented here for the record:

- `~/.claude/settings.json` — added `Bash(pushing-dispatch:*)` and
  `Bash(dispatch:*)` to the allow-list (Claude Code runs dispatch with no prompt).
- `~/.pi/agent/AGENTS.md` — added the "use Pushing Dispatch" routing rule.
- `~/.zshrc` (`CCGLM` launcher) — `CLAUDE_CODE_SUBAGENT_MODEL` changed from raw
  `glm-5.1` to the alias `sonnet`. **Why:** the Claude Code harness rejects raw
  GLM model ids for subagents ("model may not exist / no access") even though the
  Z.ai endpoint serves `glm-5.1` fine (verified HTTP 200). `sonnet` remaps to
  `glm-5.1` via `ANTHROPIC_DEFAULT_SONNET_MODEL`, so subagents run on glm-5.1
  through an accepted alias. Takes effect in new sessions only.
- `~/.codex/switch-account.sh` — added `cerafica` slot.
- `~/.codex/login-cerafica.sh` — one-shot CERAFICA onboarding helper. CERAFICA
  (`simon@cerafica.com`) is now logged in; all 3 OpenAI accounts (icloud,
  puenteworks, cerafica) are load-balanced across the codex lanes.

## Harness enablement (Claude Code / Codex / pi)
All three know to use Dispatch and can run its full surface (route, task,
breakout, doctor, list, status, kill, budget, questions, answer, checkpoint):
- Claude Code: CLAUDE.md rule + settings.json allow-list.
- Codex: `~/.codex/AGENTS.md` + `approval_policy=never` + full-access sandbox.
- pi: `~/.pi/agent/AGENTS.md` rule; runs read-only commands freely.

## Operational notes / open items
- **OpenAI/Codex out of usage until 2026-05-31.** The 6 codex lanes (codex,
  openai-gpt55, -high, -xhigh, openai-mini, codex-spark) were parked in cooldown
  (~24h) so routing auto-falls-back to GLM (hard coding), Opus (breakout/consult),
  Haiku (trivial). `codex-oss` (local Ollama) left available. They auto-restore.
  Tomorrow: run `codex login` to refresh the puenteworks token (it showed a
  stale "refresh token already used" error from account switching), then either
  let cooldowns expire or clear them:
  `python3 -c "from dispatch_lib import lane_health as L; [L.recover(x) for x in ['codex','openai-gpt55','openai-gpt55-high','openai-gpt55-xhigh','openai-mini','codex-spark']]"`
- Subagent dispatch via the Claude Code Agent tool requires a NEW session for the
  `CCGLM` `sonnet`-alias fix to take effect.
- Learning loop is built but `learning=false`; enable once `outcomes.jsonl` has data.

## Companion: Dispatch Monitor
`~/Downloads/Dispatch_monitor.zip` → source moved to `~/workspaces/Dispatch_monitor/`.
Built and installed `/Applications/DispatchMonitor.app` (menu-bar app + bundled
poller writing `monitor_state.json` every 5s). Running.
