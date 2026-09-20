"""CWD lock: prevent two active workers from racing one working directory.

Wave-2 remediation for FM-20 (Jul-18 incident: double-dispatched workers
colliding in a single worktree while external git reset underneath).

Lock store: <dispatch_root>/locks/cwd/<sha256(cwd)>.json holding
{worker_id, cwd, ts}. A lock is stealable when its holder's status is
terminal (done/errored/blocked/killed/needs_guidance) or missing.
"""

import hashlib
import json
import os
import time
from pathlib import Path

from .path_conventions import dispatch_root
from .status_writer import is_terminal, read_status


def _lock_dir() -> Path:
    d = dispatch_root() / "locks" / "cwd"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _lock_path(cwd: str) -> Path:
    key = hashlib.sha256(cwd.encode()).hexdigest()[:24]
    return _lock_dir() / f"{key}.json"


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def acquire(worker_id: str, cwd: str):
    """Try to lock cwd for worker_id. Returns (ok, holder_dict_or_None)."""
    p = _lock_path(cwd)
    if p.exists():
        try:
            holder = json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            holder = None
        if holder and holder.get("worker_id") != worker_id:
            st = read_status(holder["worker_id"])
            if st is not None and not is_terminal(st.get("current_phase", "")):
                return False, holder
        # stale (terminal or unreadable holder) — steal below
    p.write_text(json.dumps({"worker_id": worker_id, "cwd": cwd, "ts": time.time()}))
    return True, None


def release(worker_id: str) -> None:
    """Durably drop cwd locks held by worker_id. Safe to call repeatedly."""
    root = _lock_dir()
    for p in root.glob("*.json"):
        try:
            if json.loads(p.read_text()).get("worker_id") == worker_id:
                p.unlink(missing_ok=True)
        except json.JSONDecodeError:
            continue
    # Always sync, including a retry after a prior unlink whose directory sync
    # failed.  Absence is not a durable fact until this edge succeeds.
    _fsync_directory(root)


def held_by(worker_id: str) -> bool:
    """Return whether a readable cwd lock still names ``worker_id``."""
    for path in _lock_dir().glob("*.json"):
        try:
            if json.loads(path.read_text()).get("worker_id") == worker_id:
                return True
        except (json.JSONDecodeError, OSError):
            continue
    return False
