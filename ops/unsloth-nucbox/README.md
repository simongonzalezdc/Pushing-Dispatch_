# ops/unsloth-nucbox

Shared pointer for the optional NUCBox / Ornith local coding leaf used by Pushing Dispatch.

## What this directory is for

When a checkout includes the local fleet overlay, this tree holds operator notes and launch helpers for the sticky local workhorse lane (`unsloth-nucbox` / Ornith). Not every GitHub or Forgejo mirror snapshot is required to carry the full operator tree.

## Dual-host README contract

This file is intentionally mirror-safe:

- It documents the *role* of the leaf, not host-private network endpoints.
- Concrete base URLs, Tailscale names, CGNAT addresses, and machine-local paths belong in operator-private config or host-local overlays — not in the shared README.
- If sibling files (launchers, systemd drop-ins, pi-agent settings, skill blocks) are absent from a given mirror, treat them as not shipped on that snapshot rather than as broken documentation.

## How agents should use it

1. Prefer the live matrix / Dispatch routing for executor selection.
2. Use the sticky local leaf only for bounded coding/general work that policy admits.
3. Keep broad, visual, breakout, consult, and long-context work on stronger non-local tiers.
4. For provider setup, see [docs/PROVIDERS.md](../../docs/PROVIDERS.md) at the repo root.

## Parity note

GitHub and Forgejo corresponding mirrors must keep this README path in byte lockstep. Expanding or trimming operator-private material under this directory is a host overlay concern and must not reintroduce README drift.
