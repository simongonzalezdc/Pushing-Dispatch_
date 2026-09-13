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

Inheritance boundary (deliberate, not accidental environment behavior):

- ``cmd_start`` inherits the deadline bound carried by its launch lineage via
  the ``DISPATCH_DEADLINE`` environment variable. The effective bound is the
  EARLIEST of the inherited and explicit values, resolved before any side
  effect: a later ``--deadline`` can never extend an inherited (possibly
  already-expired) bound.
- ``answer`` and ``checkpoint continue`` inherit the RESUME lineage bound
  from the prior worker's stored status ``deadline`` field. The answering
  controller's own environment is NOT an applicable bound; the relaunched
  child's environment is set (or scrubbed) to exactly the resolved value so
  a stale controller variable cannot silently bind an unrelated deadline.

Degenerate inherited values fail closed: an inherited value that is present
but empty (or non-string) is corrupt metadata, not a missing deadline, and
must not manufacture an unbounded resume.
"""

import math
from datetime import datetime, timezone


DEADLINE_ENV_VAR = "DISPATCH_DEADLINE"


def _parse_candidate(value: str) -> tuple[datetime | None, str]:
    """Parse one non-empty string deadline.

    Returns ``(stamp, "")`` for a valid, timezone-aware, unexpired timestamp,
    or ``(None, reason)`` with a DEADLINE_* rejection line otherwise.
    """
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None, f"DEADLINE_MALFORMED: deadline={value} is not a parseable ISO-8601 timestamp"
    if stamp.tzinfo is None:
        return None, (
            f"DEADLINE_AMBIGUOUS_TZ: deadline={value} has no timezone offset; "
            "append Z or +HH:MM so the deadline is unambiguous"
        )
    remaining = (stamp - datetime.now(timezone.utc)).total_seconds()
    if not math.isfinite(remaining) or remaining <= 0:
        return None, f"DEADLINE_EXCEEDED: deadline={value}"
    return stamp, ""


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
    stamp, reason = _parse_candidate(value)
    return stamp is not None, reason


def resolve_effective_deadline(
    explicit,
    inherited=None,
    source: str = "inherited DISPATCH_DEADLINE",
) -> tuple[bool, str, str | None]:
    """Resolve the effective deadline before any side effect.

    Combines the explicit ``--deadline`` value with the applicable inherited
    bound (launch-lineage env at ``start``, stored prior status at
    ``answer``/``checkpoint continue``).

    Returns ``(ok, reason, effective)``:

    - ``ok=False`` — admission must reject (exit 6); ``reason`` names the
      DEADLINE_* violation, noting the inherited ``source`` when the
      inherited bound is the offender. Inherited bounds are validated first:
      a supplied later value must not mask or extend them.
    - ``ok=True`` — ``effective`` is the raw string of the EARLIEST
      applicable bound (carried forward verbatim into status and the launch
      environment), or ``None`` when no bound applies (genuinely unbounded —
      distinct from corrupt inherited metadata, which rejects).
    """
    bounds: list[tuple[datetime, str]] = []
    if inherited is not None:
        if not isinstance(inherited, str) or inherited == "":
            return False, (
                f"DEADLINE_MALFORMED: {source}={inherited!r} is not a usable "
                "ISO-8601 deadline; corrupt inherited metadata must not resume "
                "as unbounded"
            ), None
        stamp, reason = _parse_candidate(inherited)
        if stamp is None:
            return False, f"{reason} ({source})", None
        bounds.append((stamp, inherited))
    if explicit is not None and explicit != "":
        if not isinstance(explicit, str):
            return False, f"DEADLINE_MALFORMED: deadline={explicit!r} is not an ISO-8601 string", None
        stamp, reason = _parse_candidate(explicit)
        if stamp is None:
            return False, reason, None
        bounds.append((stamp, explicit))
    if not bounds:
        return True, "", None
    bounds.sort(key=lambda item: item[0])
    return True, "", bounds[0][1]
