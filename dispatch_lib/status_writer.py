"""
Worker status file management.

Status files are JSON documents written atomically (tmp + rename)
so concurrent readers never see partial writes.

Schema version 3:
  worker_id, mode, executor, parent_id, depth,
  dispatched_by_session_id, current_phase, pid, started_at,
  tokens_in, tokens_out, turns_taken, log_path, brief_path,
  finalized_at, exit_code, error_summary
"""

import json
import os
import tempfile
import time
from pathlib import Path

from .path_conventions import status_path, ensure_dirs

SCHEMA_VERSION = 3

PHASES = {
    "starting",
    "reading",
    "thinking",
    "writing",
    "done",
    "errored",
    "blocked",
    "needs_guidance",
    "killed",
    "awaiting_checkpoint",
}


def init_status(
    worker_id: str,
    mode: str,
    executor: str,
    pid: int,
    brief_path: str = "",
    log_file: str = "",
    parent_id: str = None,
    depth: int = 0,
    session_id: str = None,
) -> dict:
    """Create and write initial status file for a new worker."""
    ensure_dirs()
    status = {
        "schema_version": SCHEMA_VERSION,
        "worker_id": worker_id,
        "mode": mode,
        "executor": executor,
        "parent_id": parent_id,
        "depth": depth,
        "dispatched_by_session_id": session_id or os.environ.get("DISPATCH_SESSION_ID"),
        "current_phase": "starting",
        "pid": pid,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "tokens_in": 0,
        "tokens_out": 0,
        "turns_taken": 0,
        "log_path": log_file,
        "brief_path": brief_path,
        "finalized_at": None,
        "exit_code": None,
        "error_summary": None,
    }
    _write_atomic(worker_id, status)
    return status


def set_phase(worker_id: str, phase: str):
    """Update the current_phase field."""
    if phase not in PHASES:
        raise ValueError(f"Unknown phase: {phase}. Valid: {PHASES}")
    status = read_status(worker_id)
    if status:
        status["current_phase"] = phase
        _write_atomic(worker_id, status)


def update_tokens(worker_id: str, tokens_in: int, tokens_out: int, turns: int):
    """Update token counters."""
    status = read_status(worker_id)
    if status:
        status["tokens_in"] = tokens_in
        status["tokens_out"] = tokens_out
        status["turns_taken"] = turns
        _write_atomic(worker_id, status)


def finalize(worker_id: str, phase: str, exit_code: int = 0, error_summary: str = None):
    """Mark worker as terminal (done, errored, blocked, killed, needs_guidance)."""
    status = read_status(worker_id)
    if status:
        status["current_phase"] = phase
        status["exit_code"] = exit_code
        status["error_summary"] = error_summary
        status["finalized_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        _write_atomic(worker_id, status)


def read_status(worker_id: str) -> dict | None:
    """Read a worker's status file. Returns None if not found."""
    path = status_path(worker_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def is_terminal(phase: str) -> bool:
    """Check if a phase is terminal (worker won't transition further)."""
    return phase in {"done", "errored", "blocked", "killed", "needs_guidance"}


def _write_atomic(worker_id: str, data: dict):
    """Write status JSON atomically via tmp + rename."""
    path = status_path(worker_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.rename(tmp, str(path))
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
