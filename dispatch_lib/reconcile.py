"""Fail-closed reconciliation for worker status rows.

The dispatcher can outlive a wrapper that exits before its terminal status
write.  Reconciliation only promotes one fact to a terminal receipt: the
recorded process is definitively absent.  Ambiguous process state is retained
for operator review.
"""

from __future__ import annotations

import os
from collections.abc import Callable

from .status_writer import is_terminal


ProcessProbe = Callable[[int], str]
PROCESS_PHASES = frozenset({"starting", "reading", "thinking", "writing"})


def process_state(pid: int) -> str:
    """Return ``alive``, ``absent``, or ``unknown`` for a positive PID."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return "absent"
    except (PermissionError, OSError, OverflowError):
        return "unknown"
    return "alive"


def orphaned_reason(status: dict, probe: ProcessProbe = process_state) -> str | None:
    """Return a reconciliation reason only for a provably orphaned worker.

    ``awaiting_checkpoint`` has no live process by design and remains an
    operator-visible workflow state.  A finalized or terminal row is already
    a receipt.  Missing, malformed, live, or uninspectable PIDs fail closed.
    """
    phase = status.get("current_phase")
    if phase == "awaiting_checkpoint" or is_terminal(phase or ""):
        return None
    if phase not in PROCESS_PHASES:
        return None
    if status.get("finalized_at") is not None:
        return None
    pid = status.get("pid")
    if type(pid) is not int or pid <= 0:
        return None
    if probe(pid) != "absent":
        return None
    return "recorded process is absent"
