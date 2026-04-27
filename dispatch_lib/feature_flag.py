"""
Feature flags for dispatch rollout.

Nested dispatch and other gated features are controlled via
environment variables. This keeps the rollout incremental:
ship the code, enable via env var when ready.
"""

import os


def is_nested_dispatch_enabled() -> bool:
    """Check if nested dispatch is enabled.

    Controlled by DISPATCH_NESTED env var.
    Default: off (disabled).
    """
    return os.environ.get("DISPATCH_NESTED", "0") == "1"


def get_depth_cap() -> int:
    """Get the maximum nesting depth.

    Default: 1 (top-level workers can dispatch one level of sub-workers).
    Design target: 3. Ramp gradually with cost monitoring.

    Controlled by DISPATCH_MAX_DEPTH env var.
    """
    try:
        return int(os.environ.get("DISPATCH_MAX_DEPTH", "1"))
    except ValueError:
        return 1


def get_current_depth() -> int:
    """Get this worker's current nesting depth.

    Set by the dispatcher at launch time via DISPATCH_CURRENT_DEPTH.
    0 for top-level workers.
    """
    try:
        return int(os.environ.get("DISPATCH_CURRENT_DEPTH", "0"))
    except ValueError:
        return 0


def get_budget_remaining() -> float | None:
    """Get remaining budget from parent (if set).

    Set by parent dispatcher via DISPATCH_BUDGET_REMAINING.
    None if uncapped.
    """
    val = os.environ.get("DISPATCH_BUDGET_REMAINING", "")
    if not val:
        return None
    try:
        return float(val)
    except ValueError:
        return None


def get_deadline() -> str | None:
    """Get inherited deadline (ISO-8601) from parent.

    Set by parent dispatcher via DISPATCH_DEADLINE.
    None if no deadline.
    """
    return os.environ.get("DISPATCH_DEADLINE") or None
