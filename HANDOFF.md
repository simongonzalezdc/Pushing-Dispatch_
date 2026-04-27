# Handoff: ai-dispatch Public Repo Build

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
gh repo create ai-dispatch --private --source=. --push
```

## Items to Sanity-Check Before Public Flip

1. **README tone and accuracy** -- does it represent the project correctly?
2. **License choice** -- MIT is used (handoff recommended Apache 2.0; MIT was specified in the brief). Confirm preference.
3. **Repo name** -- "ai-dispatch" recommended. Confirm before creating GitHub remote.
4. **API endpoint URLs** -- moonshot.ai/anthropic and deepseek.com/anthropic are publicly documented. Verify they're current.
5. **Model IDs** -- claude-opus-4-6, claude-sonnet-4-6, claude-haiku-4-5-20251001, kimi-k2.6, deepseek-chat. Verify these are the IDs you want in the public example.
6. **Issue templates** -- review the three seeded issues for relevance.
7. **CLAUDE.md size** -- 53 lines, well under the 150-line cap recommended in the handoff.

## Commit History

4 commits on `main`:
1. `feat: add core Python dispatch framework` -- cli, dispatch_lib, breakout, skeleton_lint
2. `feat: add shell wrappers and shared execution library` -- _exec.sh, provider wrappers
3. `feat: add dispatch matrix, packs, hooks, and commands` -- config, packs, auto-poll
4. `docs: add comprehensive documentation, examples, and tooling` -- all docs, examples, scripts
