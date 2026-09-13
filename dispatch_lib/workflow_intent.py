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
_RECORD_KEYS = {
    "schema_version", "operation_id", "parameters", "parameters_sha256",
    "state", "created_at_ns", "updated_at_ns", "worker_id", "pid",
}


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
    required = _RECORD_KEYS - {"worker_id", "pid"}
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


def record_launch_intent(operation_id: str, parameters: dict) -> dict:
    """Create one intent, or return the identical retryable non-started intent."""
    path = _intent_path(operation_id)
    if not isinstance(parameters, dict):
        raise IntentConflict("invalid intent parameters")
    digest = hashlib.sha256(_canonical(parameters)).hexdigest()
    with _locked(path):
        if path.exists():
            record = _load_valid_record(path, operation_id)
            if record.get("parameters_sha256") != digest:
                raise IntentConflict("operation_id reused with changed parameters")
            if record.get("state") != "launch_not_started":
                raise IntentConflict(
                    f"operation requires reconciliation: {record.get('state')}"
                )
            record.pop("worker_id")
            record["state"] = "launch_requested"
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
        }
        _write(path, record)
        return record


def transition(operation_id: str, expected: str, state: str, **fields) -> dict:
    if expected not in _STATES or state not in _STATES:
        raise IntentConflict("invalid intent state")
    path = _intent_path(operation_id)
    if set(fields) - {"worker_id", "pid"}:
        raise IntentConflict("invalid intent transition fields")
    if "worker_id" in fields and not isinstance(fields["worker_id"], str):
        raise IntentConflict("invalid intent worker_id")
    if "pid" in fields and (type(fields["pid"]) is not int or fields["pid"] <= 0):
        raise IntentConflict("invalid intent pid")
    with _locked(path):
        if not path.exists():
            raise IntentConflict("intent missing")
        record = _load_valid_record(path, operation_id)
        if record.get("state") != expected:
            raise IntentConflict(
                f"intent state changed: expected {expected}, got {record.get('state')}"
            )
        record.update(fields)
        record["state"] = state
        record["updated_at_ns"] = time.time_ns()
        _validate_record(record, operation_id)
        _write(path, record)
        return record
