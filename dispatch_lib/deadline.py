"""Common deadline admission for every dispatch entrypoint.

Semantics mirror the accepted containment primitive's admission
(``seconds_remaining`` in chief-scientist/research/operational-closeout/
deadline_guard.py, sha256 775bc049d04619481e539b5a01da216d5f3f1fc73d7d26203dfc2091e23cd33c):
parse ISO-8601, require an explicit timezone, reject non-positive remaining
time. The primitive file itself is NOT vendored — it carries process-group
signal machinery irrelevant to admission, and the frozen originals stay in
the chief-scientist workspace.

Failure philosophy: fail closed. A malformed or timezone-ambiguous supplied
deadline is rejected, never silently admitted. A MISSING deadline admits —
a task without a deadline is not an expired task.
"""

import math
from datetime import datetime, timezone


def evaluate_deadline(value) -> tuple[bool, str]:
    """Admission verdict for one candidate --deadline value.

    Returns ``(ok, reason)``. ``reason`` is "" when the value is admitted,
    otherwise a human-readable DEADLINE_* rejection line for the operator.
    Callers reject with exit code 6 (the established deadline exit code).
    """
    if value is None or value == "":
        return True, ""
    if not isinstance(value, str):
        return False, f"DEADLINE_MALFORMED: deadline={value!r} is not an ISO-8601 string"
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return False, f"DEADLINE_MALFORMED: deadline={value} is not a parseable ISO-8601 timestamp"
    if stamp.tzinfo is None:
        return False, (
            f"DEADLINE_AMBIGUOUS_TZ: deadline={value} has no timezone offset; "
            "append Z or +HH:MM so the deadline is unambiguous"
        )
    remaining = (stamp - datetime.now(timezone.utc)).total_seconds()
    if not math.isfinite(remaining) or remaining <= 0:
        return False, f"DEADLINE_EXCEEDED: deadline={value}"
    return True, ""
