# Nested Dispatch Deep Dive

## Overview

Workers can spawn sub-workers via the same CLI the orchestrator uses. This enables fan-out patterns where a parent decomposes a large task into smaller, independent subtasks.

## Safety Rails

### Budget Cascade

The parent's budget includes all children's spend. When spawning a child, the parent passes `--budget-remaining` (its own remaining budget). The child's spend accrues to the parent's budget line.

**Why parent-owns-cap:** Giving children independent budgets creates a multiplication attack. N children each with a full quota bypasses the parent's cap entirely.

### Permissions Matrix

Encoded in `dispatch_matrix.toml` under `[nested_dispatch.permissions]`. Rules:

- **Self-dispatch always denied.** Sonnet spawning Sonnet, Opus spawning Opus: unbounded cost spirals.
- **Leaf executors cannot dispatch.** Haiku, local models: they should not orchestrate.
- **Cost-asymmetric chains blocked.** A metered parent spawning an expensive subscription child inverts the cost model.

### Depth Cap

Default: 1 (one level of sub-workers). Design target: 3. Ramp via `DISPATCH_MAX_DEPTH` env var.

Depth levels:
- Depth 0: Top-level worker dispatched from main session
- Depth 1: Sub-worker dispatched by depth-0 worker
- Depth 2: Sub-sub-worker (requires depth cap >= 2)

### Kill Cascade

`kill <worker-id>` walks the tree bottom-up: kills leaves first, then parents. This prevents orphan races.

`--no-cascade` flag kills only the target, letting children finish.

### Deadline Inheritance

Children inherit the parent's wall-clock deadline. A child outliving its parent is a budget leak. The dispatcher refuses to spawn a child whose estimated runtime would exceed the inherited deadline (exit code 6).

## Failure Semantics

No automatic retry. Ever. The parent polls child status and decides:
- Re-dispatch with different executor
- Handle the subtask inline
- Report failure upward

Auto-retry without diagnosis is how cost incidents happen.

## Environment Variables

Workers in a nested dispatch context receive:

| Variable | Description |
|----------|-------------|
| `DISPATCH_NESTED` | "1" if nested dispatch is enabled |
| `DISPATCH_WORKER_ID` | This worker's ID |
| `DISPATCH_CURRENT_DEPTH` | Nesting depth (0 for top-level) |
| `DISPATCH_BUDGET_REMAINING` | Remaining budget from parent |
| `DISPATCH_DEADLINE` | ISO-8601 deadline |
| `DISPATCH_MAX_DEPTH` | Maximum allowed depth |
