# SCHEMA.md — MODELS-LEDGER.json

Per-executor model intelligence for the MODEL-INTEL loop (`.omx/plans/model-intel-loop.md`, P1).
One row per executor in `dispatch_matrix.toml`. Since S4 (2026-08-20) every
executor stanza in the matrix carries `pricing_class` — the matrix is the source
of truth for configuration INCLUDING pricing_class (hard-error, no silent
default); ledger pricing-class rows derive from it at the row's `provenance` sha.
What stays ledger-side: provenance, `first_seen`, stewardship `notes`, and the
`pricing_class_sources` evidence list; benchmarks + our outcome scorecard are
later versions (P2+), filled by research sweeps and P2+ components.

## Top level

| Key | Type | Meaning |
|---|---|---|
| `schema_version` | int | 1 |
| `generated` | ISO-8601 UTC | When this file was written |
| `source` | string | The matrix version backfilled from |
| `pricing_class_sources` | [string] | Evidence used to assign pricing classes |

## Entry fields (required)

| Field | Type | Meaning |
|---|---|---|
| `name` | string | Executor key, identical to `[executors.<name>]` in the matrix |
| `provider` | string | Matrix `provider` (routing family, not the vendor) |
| `model_id` | string | Matrix `model_id` verbatim |
| `capabilities` | [string] | Matrix `capabilities` verbatim (e.g. `["vision"]`); enrichment (video, etc.) comes from research sweeps, not backfill |
| `context_window` | int \| null | Tokens, from matrix `context_window`; null = not set in matrix |
| `pricing_class` | enum | See below |
| `display_name` | string | Matrix `display_name` (emoji included) |
| `first_seen` | YYYY-MM-DD | Date the executor stanza first appeared in `dispatch_matrix.toml` git history |
| `provenance` | sha | Commit sha of the matrix version this row was extracted from (P13) |

## Optional fields

- `reasoning_effort` — string. Codex effort variants only (luna=xhigh, terra=high, sol=low, sol-high=high). Two executors can share a `model_id`; this field is what distinguishes them.
- `notes` — string. Stewardship caveats (dying subs, flash-only policies, disabled lanes, quota shapes).

## pricing_class enum

| Class | Rule | Examples |
|---|---|---|
| `prepaid-yearly` | Sunk prepaid yearly cost, $0 incremental monthly (CEO 2026-08-21 designation in matrix comments / SUBSCRIPTIONS.yaml) | kimi-*, zai-glm, minimax-m3 |
| `scarce` | Matrix budget note 2026-08-16: downgraded paid plans — reserve for lanes they're genuinely best at; avoid wide fan-outs | codex-*, grok-build |
| `credit` | Pay-as-you-go API balance; metered against a floor | dsh, deepseek-v4-pro/flash |
| `free` | $0 incremental: free tier or included with an existing subscription | kilo-free-auto, agy-gemini-flash (Workspace-included) |
| `local` | Self-hosted hardware; never quota-dead, GPU-window laws apply | lm-studio, ollama-xps-gpu, nucbox-champion |

## Update discipline

- Backfill (this file) mirrors the matrix at the `provenance` sha — no judgment beyond the
  documented pricing-class rules above.
- New rows: model-drop radar detects → research task fills the row with provenance + date →
  matrix patch adds the executor ALONGSIDE the old one (never destructive).
- Benchmarks and outcome scorecards attach in later schema versions (P2+); raw scores are
  never verdicts. Version replacement requires outcome evidence, never launch day.
