---
name: "Cost tracking dashboard"
about: "Terminal dashboard showing per-provider, per-tree, daily spend"
title: "feat: Implement cost-tracking dashboard via budget --dashboard"
labels: ["enhancement", "good first issue"]
assignees: []
---

## Summary

The budget JSONL data is already collected. A terminal dashboard showing per-provider, per-tree, daily spend would be immediately useful.

## Scope

- One new CLI subcommand flag: `python cli.py budget --dashboard`
- Terminal UI using `rich` or `textual` (optional dependency)
- Fallback to plain-text table if rich is not installed
- Shows: today's spend by provider, per-tree breakdown, running totals, top-5 most expensive workers

## Design considerations

- The dashboard should work with the existing JSONL budget ledger
- Consider a `--watch` mode that refreshes every N seconds
- Provider-specific pricing (from `dispatch_pricing.toml` or matrix defaults)

## Acceptance criteria

- [ ] Dashboard renders correctly with sample budget data
- [ ] Works without `rich` installed (fallback mode)
- [ ] Shows per-tree spend breakdown
- [ ] Shows per-provider aggregation
