"""Fail-closed, recoverable reconciliation for worker status rows."""

from __future__ import annotations

import json
import os
import re
import stat
import tempfile
import time
import uuid
from collections.abc import Callable
from pathlib import Path

from .current_worker_index import WORKER_ID, build_index, read_indexed_status
from .path_conventions import reconcile_pending_dir, status_dir
from .status_writer import is_terminal


ProcessProbe = Callable[[int], str]
PROCESS_PHASES = frozenset({"starting", "reading", "thinking", "writing"})
INTENT_SCHEMA = "pushing-dispatch-reconcile/v1"
TRANSACTION_ID = re.compile(r"^[0-9a-f]{32}$")
MAX_INTENTS = 128
MAX_INTENT_BYTES = 16 * 1024


class ReconciliationIncomplete(RuntimeError):
    """The bounded source or a pending transaction could not be proven safe."""


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
    """Return a reason only for a known process phase with an absent process."""
    phase = status.get("current_phase")
    if phase == "awaiting_checkpoint" or is_terminal(phase or ""):
        return None
    if phase not in PROCESS_PHASES or status.get("finalized_at") is not None:
        return None
    pid = status.get("pid")
    if type(pid) is not int or pid <= 0:
        return None
    if probe(pid) != "absent":
        return None
    return "recorded process is absent"


def bounded_status_snapshot() -> list[dict]:
    """Return a complete bounded snapshot of filename-bound current statuses."""
    root = status_dir()
    if not root.exists():
        return []
    result = build_index(root)
    if not result["source_generation"]["consistent"]:
        result = build_index(root)
    coverage = result["coverage"]
    if not coverage["complete"]:
        reason = coverage.get("stop_reason") or "INCOMPLETE"
        raise ReconciliationIncomplete(f"current-worker snapshot incomplete: {reason}")
    statuses = []
    for worker_id in result["candidate_worker_ids"]:
        value = read_indexed_status(root, worker_id)
        if value is not None:
            statuses.append(value)
    return statuses


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def make_intent(worker_id: str, expected_phase: str, reason: str) -> dict:
    if WORKER_ID.fullmatch(worker_id) is None or expected_phase not in PROCESS_PHASES:
        raise ReconciliationIncomplete("refusing unsafe reconciliation intent")
    return {
        "schema": INTENT_SCHEMA,
        "transaction_id": uuid.uuid4().hex,
        "worker_id": worker_id,
        "expected_phase": expected_phase,
        "reason": reason,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def _validate_intent(value: object, worker_id: str) -> dict:
    expected = {
        "schema",
        "transaction_id",
        "worker_id",
        "expected_phase",
        "reason",
        "created_at",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise ReconciliationIncomplete("malformed pending reconciliation intent")
    if (
        value["schema"] != INTENT_SCHEMA
        or value["worker_id"] != worker_id
        or TRANSACTION_ID.fullmatch(str(value["transaction_id"])) is None
        or value["expected_phase"] not in PROCESS_PHASES
        or value["reason"] != "recorded process is absent"
        or not isinstance(value["created_at"], str)
    ):
        raise ReconciliationIncomplete("invalid pending reconciliation intent")
    return value


def load_intents() -> list[dict]:
    root = reconcile_pending_dir()
    if not root.exists():
        return []
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        directory = os.open(root, flags)
    except OSError as error:
        raise ReconciliationIncomplete(
            "unsafe pending reconciliation directory"
        ) from error
    intents = []
    try:
        entries = sorted(os.scandir(directory), key=lambda item: item.name)
        if len(entries) > MAX_INTENTS:
            raise ReconciliationIncomplete("too many pending reconciliation intents")
        for entry in entries:
            if not entry.name.endswith(".json"):
                raise ReconciliationIncomplete(
                    "unexpected pending reconciliation entry"
                )
            worker_id = entry.name[:-5]
            if WORKER_ID.fullmatch(worker_id) is None:
                raise ReconciliationIncomplete("unsafe pending reconciliation name")
            child = None
            try:
                child = os.open(
                    entry.name,
                    os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=directory,
                )
                info = os.fstat(child)
                if (
                    not stat.S_ISREG(info.st_mode)
                    or info.st_uid != os.geteuid()
                    or info.st_size > MAX_INTENT_BYTES
                ):
                    raise ReconciliationIncomplete(
                        "unsafe pending reconciliation intent"
                    )
                raw = os.read(child, MAX_INTENT_BYTES + 1)
                if len(raw) > MAX_INTENT_BYTES:
                    raise ReconciliationIncomplete(
                        "oversized pending reconciliation intent"
                    )
                intents.append(_validate_intent(json.loads(raw), worker_id))
            except (UnicodeDecodeError, json.JSONDecodeError, OSError) as error:
                raise ReconciliationIncomplete(
                    "unreadable pending reconciliation intent"
                ) from error
            finally:
                if child is not None:
                    os.close(child)
    finally:
        os.close(directory)
    return intents


def store_intent(intent: dict) -> None:
    worker_id = str(intent.get("worker_id", ""))
    _validate_intent(intent, worker_id)
    root = reconcile_pending_dir()
    root.mkdir(parents=True, exist_ok=True)
    destination = root / f"{worker_id}.json"
    if destination.exists():
        existing = next(
            (item for item in load_intents() if item["worker_id"] == worker_id), None
        )
        if existing == intent:
            return
        raise ReconciliationIncomplete(
            "worker already has a pending reconciliation intent"
        )
    descriptor, temporary = tempfile.mkstemp(prefix=".intent-", dir=root)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(intent, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
        _fsync_directory(root)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def remove_intent(worker_id: str) -> None:
    if WORKER_ID.fullmatch(worker_id) is None:
        raise ReconciliationIncomplete("unsafe pending reconciliation name")
    root = reconcile_pending_dir()
    (root / f"{worker_id}.json").unlink()
    _fsync_directory(root)


def reconciliation_summary(intent: dict) -> str:
    return f"Orphan reconciled ({intent['transaction_id']}): {intent['reason']}"


def status_matches_reconciliation(status: dict | None, intent: dict) -> bool:
    return bool(
        status
        and status.get("worker_id") == intent["worker_id"]
        and status.get("current_phase") == "errored"
        and status.get("exit_code") == 70
        and status.get("finalized_at") is not None
        and status.get("error_summary") == reconciliation_summary(intent)
    )
