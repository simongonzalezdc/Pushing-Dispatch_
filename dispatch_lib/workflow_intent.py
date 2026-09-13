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
_STATES = {"launch_requested", "launch_started", "launch_not_started"}


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


def record_launch_intent(operation_id: str, parameters: dict) -> dict:
    """Create one intent, or return the identical retryable non-started intent."""
    path = _intent_path(operation_id)
    digest = hashlib.sha256(_canonical(parameters)).hexdigest()
    with _locked(path):
        if path.exists():
            record = json.loads(path.read_text())
            if record.get("parameters_sha256") != digest:
                raise IntentConflict("operation_id reused with changed parameters")
            if record.get("state") != "launch_not_started":
                raise IntentConflict(
                    f"operation requires reconciliation: {record.get('state')}"
                )
            record["state"] = "launch_requested"
            record["updated_at_ns"] = time.time_ns()
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
    with _locked(path):
        if not path.exists():
            raise IntentConflict("intent missing")
        record = json.loads(path.read_text())
        if record.get("state") != expected:
            raise IntentConflict(
                f"intent state changed: expected {expected}, got {record.get('state')}"
            )
        record.update(fields)
        record["state"] = state
        record["updated_at_ns"] = time.time_ns()
        _write(path, record)
        return record
