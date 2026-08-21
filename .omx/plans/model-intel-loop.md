# MODEL-INTEL loop — self-updating model intelligence for the dispatch matrix

CEO order 2026-08-21: "a research self-updating component that gets all the
benchmarks, helps the matrix select which model for which task, and auto-updates
the matrix when a new model drops (GLM 5.4 for example), replacing the older
version." Trust condition (same order): routing + output quality must be
finetunable and trusted — measured, not assumed.

## What already exists (build ON these, no new wheels)
- ops/model-drop radar: daily provider-catalog sweep, NEW-MODEL banner on drift
  (landed 2d228d4) — the loop's EYES.
- outcomes.jsonl + learning=true: per-executor success/cost re-biasing
  (3,857 records) — the loop's MEMORY.
- quota_ledger + smart_route (balancer, on main): quota-aware routing — the
  loop's WALLET.
- research team 4x/day sweeps (DSH flash) + radar: benchmark/pricing intel
  collection — the loop's RESEARCHERS.

## Components to build
1. MODELS-LEDGER (repo file, json): per model+effort variant — capabilities
   (vision/video/context), pricing class (prepaid-yearly / scarce / credit /
   free / local), benchmark snapshots (sourced: public leaderboards + provider
   release notes via research sweeps; every row carries provenance + date),
   and our OWN outcome scorecard keyed by work class.
2. SELECTION ADVISOR: function joining ledger + live outcomes + quota state →
   recommends executor+effort per task class; emits proposed auto_route tier
   edits + effort-split proposals (sol-low vs sol-high class) with evidence.
3. AUTO-UPDATE PIPELINE (model drops): radar detects new model → research task
   fills a ledger row (benchmarks, pricing, capabilities) → matrix patch adds
   the new executor ALONGSIDE the old (never destructive) → smoke-test task
   (trivial+standard probes) → tier candidates shift to the new entry only
   after N clean outcomes → old entry retired (commented, prunable) once
   scorecard shows the replacement holding up. Rollback = git revert, one
   command. CEO banner on every auto-update; CEO word pins/overrides anything.
4. STEWARDSHIP RULES (encoded, from CEO law): kimi = prepaid-yearly smart
   vision/video lane — reserve for work needing it; scarce lanes (codex/grok)
   only where genuinely best; kilo = DS-flash default while credit remains;
   DSH = flash-only until CEO notice.

## Gates
- Matrix patches land via consensus micro-review (architect+critic on the
  diff) — automated, cheap, logged.
- Version REPLACEMENT requires outcome evidence, never on launch day.
- All advisor proposals carry provenance (P13); raw scores are never verdicts
  (verdicts = advisor + scorecard + CEO override).

## Build order
P1 MODELS-LEDGER schema + backfill from matrix + radar feed.
P2 advisor v1 (reads ledger, proposes tier edits as PRs to the matrix repo).
P3 auto-update pipeline (drop → ledger row → parallel entry → smoke → shift).
P4 effort-split analytics (outcome data by effort variant).
