"""Durable, local launch intents for recoverable dispatch operations.

This is deliberately a single-host file store.  It records ambiguity across a
launcher crash; it is not a cross-host lease or proof that an external effect
did (or did not) happen.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

from dispatch_lib.path_conventions import dispatch_root


_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{7,127}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_STATES = {"launch_requested", "launch_started", "launch_not_started"}
# launch_started is terminal: uncertainty after a launched effect is
# preserved, never downgraded or rewritten in place.
_LEGAL_TRANSITIONS = {
    ("launch_requested", "launch_not_started"),
    ("launch_requested", "launch_started"),
    ("launch_not_started", "launch_started"),
}
_RECORD_KEYS = {
    "schema_version", "operation_id", "parameters", "parameters_sha256",
    "state", "created_at_ns", "updated_at_ns", "worker_id", "pid",
    # Additive optional fields (schema_version stays 1; legacy records
    # without them remain valid under THIS reader. The installed ed27d1fa
    # reader rejects ANY extra key — see the dual-reader tests and the
    # adoption/rollback strategy in NEXT-SLICE-DESIGN-IDENTITY-COMPACTION.md):
    "revision",        # int >= 0, +1 on every persisted mutation
    "controller_token",  # non-empty controller identity for effect fencing
    "attempt",         # int >= 1; >= 2 only on replacement records
    "replacement_of",  # predecessor operation_id on replacement records
    "replaced_by",     # admitted replacement op on a replaced original
}

# Sentinel for a REQUIRED optimistic-concurrency argument: omission must
# raise a typed conflict, never bypass takeover fencing (CS counterexample:
# a stale controller acting with expected_revision omitted).
_UNSET = object()


class IntentConflict(RuntimeError):
    """The operation identity is invalid, changed, or already ambiguous."""


def checkpoint_operation_id(checkpoint_bytes: bytes) -> str:
    return "checkpoint-" + hashlib.sha256(checkpoint_bytes).hexdigest()


def _canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _intent_path(operation_id: str) -> Path:
    if not isinstance(operation_id, str) or not _ID_RE.fullmatch(operation_id):
        raise IntentConflict("invalid operation_id")
    return dispatch_root() / "workflow" / "intents" / f"{operation_id}.json"


@contextmanager
def _locked(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(".lock")
    with open(lock_path, "a+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        yield


@contextmanager
def _locked_many(paths: list[Path]):
    """Exclusive locks over several records in canonical (sorted) order.

    A fixed global lock order makes the two-record replacement transaction
    deadlock-free: every acquisition sequence is ascending, so a cycle can
    never form between concurrent replacements (CS collision counterexample).
    """
    locked = []
    try:
        for path in sorted(paths, key=lambda p: str(p)):
            path.parent.mkdir(parents=True, exist_ok=True)
            lock_path = path.with_suffix(".lock")
            handle = open(lock_path, "a+b")
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            locked.append(handle)
        yield
    finally:
        for handle in reversed(locked):
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()


def read_intent(operation_id: str) -> dict | None:
    """Validated read of one intent record, or None when it does not exist.

    Callers use this to learn the current revision for the mandatory CAS
    argument before an authoritative mutation. Corrupt or invalid records
    raise the same typed conflict as mutation would.
    """
    path = _intent_path(operation_id)
    if not path.exists():
        return None
    return _load_valid_record(path, operation_id)


def _write(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(_canonical(record) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp_name, path)
        dir_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def _load_valid_record(path: Path, operation_id: str) -> dict:
    """Load a complete, internally consistent intent or fail without mutation."""
    try:
        record = json.loads(path.read_bytes())
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise IntentConflict("malformed intent record") from exc

    _validate_record(record, operation_id)
    return record


def _validate_record(record: object, operation_id: str) -> None:
    """Validate both record structure and state-dependent effect evidence."""

    if not isinstance(record, dict) or set(record) - _RECORD_KEYS:
        raise IntentConflict("invalid intent record schema")
    # Required base schema; the additive fields (revision, controller_token,
    # attempt, replacement_of) and the state-dependent effect fields stay
    # optional so legacy schema-1 records validate unchanged.
    required = _RECORD_KEYS - {
        "worker_id", "pid", "revision", "controller_token", "attempt",
        "replacement_of", "replaced_by",
    }
    if not required.issubset(record):
        raise IntentConflict("invalid intent record schema")
    if type(record["schema_version"]) is not int or record["schema_version"] != 1:
        raise IntentConflict("invalid intent record schema")
    if record["operation_id"] != operation_id:
        raise IntentConflict("intent operation identity mismatch")
    if not isinstance(record["parameters"], dict):
        raise IntentConflict("invalid intent parameters")
    digest = record["parameters_sha256"]
    if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
        raise IntentConflict("invalid intent parameters digest")
    if hashlib.sha256(_canonical(record["parameters"])).hexdigest() != digest:
        raise IntentConflict("intent parameters digest mismatch")
    if not isinstance(record["state"], str) or record["state"] not in _STATES:
        raise IntentConflict("invalid intent state")
    created = record["created_at_ns"]
    updated = record["updated_at_ns"]
    if (
        type(created) is not int
        or type(updated) is not int
        or created < 0
        or updated < created
    ):
        raise IntentConflict("invalid intent timestamps")
    if "worker_id" in record and (
        not isinstance(record["worker_id"], str) or not record["worker_id"]
    ):
        raise IntentConflict("invalid intent worker_id")
    if "pid" in record and (type(record["pid"]) is not int or record["pid"] <= 0):
        raise IntentConflict("invalid intent pid")
    present = set(record) & {"worker_id", "pid"}
    expected_fields = {
        "launch_requested": set(),
        "launch_not_started": {"worker_id"},
        "launch_started": {"worker_id", "pid"},
    }[record["state"]]
    if present != expected_fields:
        raise IntentConflict("intent fields inconsistent with state")
    revision = record.get("revision")
    if revision is not None and (type(revision) is not int or revision < 0):
        raise IntentConflict("invalid intent revision")
    token = record.get("controller_token")
    if token is not None and (not isinstance(token, str) or not token):
        raise IntentConflict("invalid intent controller token")
    attempt = record.get("attempt")
    if attempt is not None and (type(attempt) is not int or attempt < 1):
        raise IntentConflict("invalid intent attempt")
    replacement_of = record.get("replacement_of")
    if replacement_of is not None:
        if (
            not isinstance(replacement_of, str)
            or not _ID_RE.fullmatch(replacement_of)
            or replacement_of == record["operation_id"]
        ):
            raise IntentConflict("invalid intent replacement linkage")
    replaced_by = record.get("replaced_by")
    if replaced_by is not None:
        if (
            not isinstance(replaced_by, str)
            or not _ID_RE.fullmatch(replaced_by)
            or replaced_by == record["operation_id"]
        ):
            raise IntentConflict("invalid intent replacement admission")
    # Replacement records (attempt >= 2) carry replacement_of; any record
    # that has admitted a successor carries replaced_by — a chained
    # replacement legitimately carries both (provenance plus admission).
    if replacement_of is not None:
        if attempt is None or attempt < 2:
            raise IntentConflict("intent attempt linkage inconsistent")
    elif attempt is not None and attempt >= 2:
        raise IntentConflict("intent attempt linkage inconsistent")


def _linked_replacements(original_operation_id: str) -> set[str]:
    """Operation ids with a persisted record linking to this original.

    The minted destination record is itself the durable pending
    reservation: it already carries ``replacement_of``, the attempt number
    and the controller token, atomically visible via the tmp+rename write.
    Scanning persisted linkage therefore makes the interrupted-completion
    boundary (destination persisted, original's ``replaced_by`` mark lost)
    discoverable by EVERY later admission, including one proposing a
    different replacement id — neither write order alone provides that.

    Called only while the original's lock is held, so a concurrent mint
    for this original is excluded by that lock. A record that cannot be
    validated fails closed: an unreadable store must not authorize a
    duplicate effect.
    """
    intents_dir = dispatch_root() / "workflow" / "intents"
    linked: set[str] = set()
    for path in sorted(intents_dir.glob("*.json")):
        operation_id = path.stem
        try:
            record = _load_valid_record(path, operation_id)
        except IntentConflict as exc:
            raise IntentConflict(
                f"unreadable intent record {path.name} during replacement "
                "scan"
            ) from exc
        except OSError as exc:
            raise IntentConflict(
                f"unreadable intent record {path.name} during replacement "
                "scan"
            ) from exc
        if record.get("replacement_of") == original_operation_id:
            linked.add(operation_id)
    return linked


def record_launch_intent(operation_id: str, parameters: dict,
                         controller_token: str | None = None,
                         expected_revision=_UNSET) -> dict:
    """Create one intent, or retry an identical authoritative non-started one.

    Creation is the one CAS-free mutation (nothing exists to fence; the
    create-or-conflict check runs under the destination lock). A RETRY of an
    existing record requires the CURRENT revision: an omitted or stale
    ``expected_revision`` raises rather than bypassing takeover fencing, so a
    controller that lost an operation cannot reclaim it blindly (CS
    counterexample). The retrying controller may rebind the controller token —
    no effect exists yet — and every rebind bumps the revision.
    """
    path = _intent_path(operation_id)
    if not isinstance(parameters, dict):
        raise IntentConflict("invalid intent parameters")
    if controller_token is not None and (
        not isinstance(controller_token, str) or not controller_token
    ):
        raise IntentConflict("invalid intent controller token")
    digest = hashlib.sha256(_canonical(parameters)).hexdigest()
    with _locked(path):
        if path.exists():
            record = _load_valid_record(path, operation_id)
            if record.get("parameters_sha256") != digest:
                raise IntentConflict("operation_id reused with changed parameters")
            if expected_revision is _UNSET or type(expected_revision) is not int:
                raise IntentConflict(
                    "expected_revision required: an existing operation cannot "
                    "be retried without acknowledging its current revision"
                )
            if expected_revision != record.get("revision", 0):
                raise IntentConflict(
                    f"stale revision: expected {expected_revision}, "
                    f"current {record.get('revision', 0)}"
                )
            if record.get("state") != "launch_not_started":
                raise IntentConflict(
                    f"operation requires reconciliation: {record.get('state')}"
                )
            record.pop("worker_id")
            record["state"] = "launch_requested"
            if controller_token is not None:
                record["controller_token"] = controller_token
            record["revision"] = record.get("revision", 0) + 1
            record["updated_at_ns"] = time.time_ns()
            _validate_record(record, operation_id)
            _write(path, record)
            return record
        record = {
            "schema_version": 1,
            "operation_id": operation_id,
            "parameters": parameters,
            "parameters_sha256": digest,
            "state": "launch_requested",
            "created_at_ns": time.time_ns(),
            "updated_at_ns": time.time_ns(),
            "revision": 0,
            "attempt": 1,
        }
        if controller_token is not None:
            record["controller_token"] = controller_token
        _write(path, record)
        return record


def transition(operation_id: str, expected: str, state: str, *,
               expected_revision=_UNSET,
               controller_token: str | None = None, **fields) -> dict:
    """Authoritative state mutation: graph-checked, identity-immutable, CAS-mandatory.

    Enforcement at this boundary, not by caller discipline:

    - ``expected_revision`` is REQUIRED and must equal the current revision.
      Omission raises; a stale value raises. This is the takeover fence: a
      controller that lost its claim (another controller bumped the revision)
      can never act again without re-reading the record, and an omitted
      argument cannot bypass that check (CS counterexample: stale A
      reclaiming after B's takeover).
    - Only the legal transitions run; ``launch_started`` is terminal, so a
      launched effect is never downgraded (uncertainty is preserved).
    - A recorded attempt/effect identity (``worker_id``, and ``pid`` once
      started) can never be replaced in place. Identical same-state replay
      returns the record without mutation; any different identity rejects.
      Replacement is ``record_replacement_intent`` — an explicitly linked new
      attempt — never an overwrite.
    - Controller fencing: a token-bound record rejects effect-boundary and
      post-effect mutations carrying a mismatching or absent token. Pre-effect
      mutations may rebind the token (audited via the revision bump); an
      unbound legacy record adopts the caller's token at the effect boundary.
    - Every persisted mutation bumps the revision.
    """
    if expected not in _STATES or state not in _STATES:
        raise IntentConflict("invalid intent state")
    path = _intent_path(operation_id)
    if set(fields) - {"worker_id", "pid"}:
        raise IntentConflict("invalid intent transition fields")
    if "worker_id" in fields and not isinstance(fields["worker_id"], str):
        raise IntentConflict("invalid intent worker_id")
    if "pid" in fields and (type(fields["pid"]) is not int or fields["pid"] <= 0):
        raise IntentConflict("invalid intent pid")
    if controller_token is not None and (
        not isinstance(controller_token, str) or not controller_token
    ):
        raise IntentConflict("invalid intent controller token")
    if expected_revision is _UNSET or type(expected_revision) is not int:
        raise IntentConflict(
            "expected_revision required: omitted CAS cannot bypass takeover fencing"
        )
    with _locked(path):
        if not path.exists():
            raise IntentConflict("intent missing")
        record = _load_valid_record(path, operation_id)
        current_state = record.get("state")
        if current_state != expected:
            raise IntentConflict(
                f"intent state changed: expected {expected}, got {current_state}"
            )
        if expected != state and (expected, state) not in _LEGAL_TRANSITIONS:
            raise IntentConflict(
                f"illegal intent transition: {expected} -> {state}"
            )
        if expected_revision != record.get("revision", 0):
            raise IntentConflict(
                f"stale revision: expected {expected_revision}, "
                f"current {record.get('revision', 0)}"
            )
        bound = record.get("controller_token")
        effect_boundary = state == "launch_started" or current_state == "launch_started"
        mutated = False
        if bound is not None and effect_boundary and (
            controller_token is None or controller_token != bound
        ):
            raise IntentConflict(
                "stale controller: intent is bound to another controller token"
            )
        if bound is None and controller_token is not None:
            record["controller_token"] = controller_token
            mutated = True
        elif (
            bound is not None
            and controller_token is not None
            and controller_token != bound
        ):
            # Pre-effect rebind by a new controller process; audited below by
            # the revision bump. Effect-boundary/post-effect rebinds are
            # rejected above.
            record["controller_token"] = controller_token
            mutated = True
        # Immutable attempt/effect identity.
        identity_fields = (
            ("worker_id", "pid")
            if current_state == "launch_started" else ("worker_id",)
        )
        recorded = {k: record[k] for k in identity_fields if k in record}
        incoming = {k: fields[k] for k in identity_fields if k in fields}
        if recorded and incoming and incoming != recorded:
            raise IntentConflict(
                "attempt identity is immutable: record an explicit linked "
                "replacement attempt instead of rewriting it"
            )
        if not mutated and incoming == recorded and state == current_state:
            return record  # idempotent identical replay: no mutation
        record.update(fields)
        record["state"] = state
        record["revision"] = record.get("revision", 0) + 1
        record["updated_at_ns"] = time.time_ns()
        _validate_record(record, operation_id)
        _write(path, record)
        return record


def record_replacement_intent(original_operation_id: str,
                              replacement_operation_id: str,
                              parameters: dict,
                              controller_token: str,
                              expected_revision=_UNSET) -> dict:
    """Admit ONE explicitly linked replacement for an uncertain launched effect.

    Single fenced replacement admission (CS counterexamples repaired here):

    - The transaction holds BOTH records' locks in canonical sorted order, so
      destination uniqueness is checked inside the authoritative lock scope
      even when two originals race on the same replacement id: the loser
      rejects with the winner's bytes untouched.
    - The original may admit at most one replacement: the admission is
      recorded durably on the original as ``replaced_by`` (state, attempt and
      effect identity untouched; revision bumped). A second, distinct
      replacement id for the same uncertain original rejects — linkage alone
      does not authorize a duplicate effect; reconciliation of the admitted
      replacement does.
    - Write order is mint-then-mark, so a crash between the two writes is
      recoverable: a retry finds the existing destination, validates linkage
      and parameters, and completes the original's admission mark. The
      minted destination record is the durable pending reservation — every
      admission also scans persisted ``replacement_of`` linkage under the
      original's lock, so after an interrupted completion (destination
      persisted, mark lost) a same-id retry completes the mark without
      rewriting the destination, and EVERY alternate replacement id rejects
      before any write. Neither write order alone provides that fence.
    - The original's current ``expected_revision`` is REQUIRED — takeover
      fencing applies to replacement admission like every other mutation.

    The replacement is always attributed: the controller token is required.
    """  # noqa: D205
    original_path = _intent_path(original_operation_id)
    replacement_path = _intent_path(replacement_operation_id)
    if not isinstance(parameters, dict):
        raise IntentConflict("invalid intent parameters")
    if replacement_operation_id == original_operation_id:
        raise IntentConflict("replacement operation_id must differ")
    if not isinstance(controller_token, str) or not controller_token:
        raise IntentConflict("invalid intent controller token")
    if expected_revision is _UNSET or type(expected_revision) is not int:
        raise IntentConflict(
            "expected_revision required: replacement admission must "
            "acknowledge the original's current revision"
        )
    digest = hashlib.sha256(_canonical(parameters)).hexdigest()
    with _locked_many([original_path, replacement_path]):
        if not original_path.exists():
            raise IntentConflict("original intent missing")
        original = _load_valid_record(original_path, original_operation_id)
        if original.get("state") != "launch_started":
            raise IntentConflict(
                "replacement requires an uncertain launched operation: "
                f"original state is {original.get('state')}"
            )
        if expected_revision != original.get("revision", 0):
            raise IntentConflict(
                f"stale revision: expected {expected_revision}, "
                f"current {original.get('revision', 0)}"
            )
        admitted = original.get("replaced_by")
        if admitted is not None and admitted != replacement_operation_id:
            raise IntentConflict(
                "original already admitted replacement "
                f"{admitted!r}; reconcile that attempt instead of "
                "admitting a duplicate effect"
            )
        minted = _linked_replacements(original_operation_id)
        minted.discard(replacement_operation_id)
        if minted:
            raise IntentConflict(
                "original already has minted replacement attempt(s) "
                f"{sorted(minted)} (interrupted completion); reconcile that "
                "attempt instead of admitting a duplicate effect"
            )
        if replacement_path.exists():
            existing = _load_valid_record(
                replacement_path, replacement_operation_id)
            if (
                existing.get("replacement_of") != original_operation_id
                or existing.get("parameters_sha256") != digest
            ):
                raise IntentConflict("replacement operation_id reused")
            replacement = existing
        else:
            replacement = {
                "schema_version": 1,
                "operation_id": replacement_operation_id,
                "parameters": parameters,
                "parameters_sha256": digest,
                "state": "launch_requested",
                "created_at_ns": time.time_ns(),
                "updated_at_ns": time.time_ns(),
                "revision": 0,
                "attempt": original.get("attempt", 1) + 1,
                "replacement_of": original_operation_id,
                "controller_token": controller_token,
            }
            _write(replacement_path, replacement)
        if admitted is None:
            original["replaced_by"] = replacement_operation_id
            original["revision"] = original.get("revision", 0) + 1
            original["updated_at_ns"] = time.time_ns()
            _validate_record(original, original_operation_id)
            _write(original_path, original)
        return replacement
