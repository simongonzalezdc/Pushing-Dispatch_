# Handoff: pushing-dispatch Public Repo Build

## What Was Built

A standalone, public-ready multi-model dispatch framework extracted from a private dispatch system. The repo contains:

- **Core Python framework** (cli.py, breakout.py, skeleton_lint.py, dispatch_lib/) implementing worker dispatch, status tracking, budget management, nested dispatch with safety rails, and auto-routing.
- **Shell wrappers** (5 providers: opus, sonnet, haiku, moonshot/kimi, deepseek) with a shared execution library (`_exec.sh`) handling brief assembly, prompt templating, and Claude Code invocation.
- **Dispatch packs** (baseline + 5 detail packs) for composable context loading.
- **Reference matrix** (`dispatch_matrix.toml.example`) with all executor definitions, routing heuristics, and permissions.
- **Comprehensive documentation** (README, INSTALL, ORCHESTRATING, CUSTOMIZATION, PROVIDERS, TROUBLESHOOTING, CONTRIBUTING).
- **LLM orientation files** (CLAUDE.md, AGENTS.md, GEMINI.md) for AI agents working in the repo.
- **3 worked examples** (code review, parallel batch, long-context summarization).
- **Utility scripts** (check-prereqs.sh, smoke-test.sh).
- **Issue templates** (3 seeded first issues: OpenAI-compat, dispatch init, budget dashboard).
- **Auto-poll hook** and **dispatch-poll command** for session-scoped worker monitoring.

## Sanitization Audit Results

### Blacklist grep results: CLEAN

All blacklist terms were searched across all `.md`, `.py`, `.sh`, `.toml` files.

| Term | Hits | Status |
|------|------|--------|
| CxN, creatioexnihilo, creatioexnihilo.com | 0 | Clean |
| f-stop, fstop | 0 | Clean |
| Pushing Squares, PUSHINGSQUARES | 0 | Clean |
| BRAINSTORMING, RESOLVED_SHADOWS, MEMORY_BANK | 0 | Clean |
| Aketon | 0 | Clean |
| Ari, Leavesley, ari_leavesley, ari_evergreen | 0 | Clean |
| CRUSH, CBA, SUBTRACKT, REFRAKT, FUZZ, GRAPHFX, CANDY | 0 | Clean |
| Clief Notes, Backstage Tech, Nihilo | 0 | Clean |
| dyslexi | 0 | Clean |
| Shadow Monitor | 0 | Clean |
| SHADOW (as workspace name) | 0 | Clean |
| Currency symbol (GBP) | 0 | Clean (all costs in USD) |
| Nikon, IBC, Printworks | 0 | Clean |

### False positive carve-outs

| Term | File | Context | Status |
|------|------|---------|--------|
| "pushed" | dispatch_packs/branch-safety.md | "Never amend commits that may have been pushed" | Generic git usage, not the tool/brand name. **Retained.** |

### What was NOT extracted

- Phase 4 swarm code (rolled back, no provider support)
- Voice containment pack (workspace-specific)
- Memory protocol pack (workspace-specific)
- Session discipline pack (workspace-specific)
- Observer/Gemma system
- Daily maintenance orchestrator
- ShadowMonitor macOS app
- Real API pricing data
- Personal config (dyslexia rules, work hours, voice rules)
- Any workspace names, client names, or plugin codenames

## Repo Location

**Local:** `/Volumes/T5 EVO/Advisor_Development_X_Dispatch`

**GitHub:** Not yet pushed. Awaiting operator review and repo name confirmation.

Suggested push command:
```bash
cd "/Volumes/T5 EVO/Advisor_Development_X_Dispatch"
gh repo create pushing-dispatch --private --source=. --push
```

## Items to Sanity-Check Before Public Flip

1. **README tone and accuracy** -- does it represent the project correctly?
2. **License choice** -- MIT is used (handoff recommended Apache 2.0; MIT was specified in the brief). Confirm preference.
3. **Repo name** -- "pushing-dispatch" recommended. Confirm before creating GitHub remote.
4. **API endpoint URLs** -- moonshot.ai/anthropic and deepseek.com/anthropic are publicly documented. Verify they're current.
5. **Model IDs** -- claude-opus-4-7, claude-sonnet-4-6, claude-haiku-4-5-20251001, kimi-k2.6, deepseek-v4-flash. Verified against live matrix 2026-04-27.
6. **Issue templates** -- review the three seeded issues for relevance.
7. **CLAUDE.md size** -- 53 lines, well under the 150-line cap recommended in the handoff.

## Parity restoration (2026-04-27)

Five deltas ported from the private dispatch codebase to restore missing capabilities:

1. **Delta 1 -- Wrapper exit-code protocol** (`bin/wrappers/_exec.sh`): The wrapper now decodes worker `Status:` tokens into documented exit codes: `0` (DONE/DONE_WITH_CONCERNS), `2` (NEEDS_GUIDANCE), `3` (BLOCKED), `4` (claude non-zero). Falls back to `0` when no status token is found on a clean exit.

2. **Delta 2 -- Checkpoint capability** (`dispatch_lib/checkpoint.py`, `cli.py`): Full phased breakout state machine restored. Supports `CHECKPOINT: pause-for-review` and `CHECKPOINT: auto-continue` directives in briefs. CLI subcommands: `checkpoint list` (shows awaiting checkpoints) and `checkpoint continue` (re-dispatches paused worker).

3. **Delta 3 -- Answer subcommand** (`cli.py`): `cli.py answer <worker-id> --answer <text>` (or `--answer-file`) re-dispatches a worker with the operator's answer appended to the original brief. Archives the old question file and creates a registry resolution event.

4. **Delta 4 -- Cost-tier guard** (`dispatch_lib/permissions.py`): Restored `_is_metered()` / `_is_subscription()` helpers and the hard rule blocking metered parents (kimi, deepseek, minimax) from spawning high-cost subscription children (opus, sonnet). Haiku is explicitly allowed as cheap/bounded.

5. **Delta 5 -- kimi.sh wrapper alias** (`bin/wrappers/kimi.sh`, `dispatch_matrix.toml.example`): Added `kimi.sh` as a thin shim that `exec`s `moonshot.sh`. Matrix example updated to use `wrapper = "kimi.sh"` for kimi and kimi-think executors so wrapper name and executor key align.

## Commit History

4 commits on `main`:
1. `feat: add core Python dispatch framework` -- cli, dispatch_lib, breakout, skeleton_lint
2. `feat: add shell wrappers and shared execution library` -- _exec.sh, provider wrappers
3. `feat: add dispatch matrix, packs, hooks, and commands` -- config, packs, auto-poll
4. `docs: add comprehensive documentation, examples, and tooling` -- all docs, examples, scripts
