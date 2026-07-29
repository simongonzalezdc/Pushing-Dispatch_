"""Serialize single-seat local leaves (Ornith / unsloth-nucbox).

Fail-fast when a second concurrent job would contend for GPU parallel=1.
Uses a PID lock file under DISPATCH_ROOT/locks/ plus status-file cross-check.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from .path_conventions import dispatch_root, status_dir
from .status_writer import is_terminal

# Executors that must run one-at-a-time on the NUC sticky leaf.
SERIALIZE_EXECUTORS = frozenset({"unsloth-nucbox"})


def locks_dir() -> Path:
    return dispatch_root() / "locks"


def lock_path_for(executor: str) -> Path:
    safe = executor.replace("/", "_")
    return locks_dir() / f"{safe}.leaf.lock"


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Exists but not ours — treat as alive.
        return True
    except OSError:
        return False
    return True


def read_lock_holder(executor: str) -> dict | None:
    path = lock_path_for(executor)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        try:
            raw = path.read_text(encoding="utf-8").strip().split()
            if not raw:
                return None
            data = {"pid": int(raw[0]), "worker_id": raw[1] if len(raw) > 1 else ""}
        except (OSError, ValueError):
            return None
    pid = int(data.get("pid") or 0)
    if not _pid_alive(pid):
        return None
    return data


def active_status_workers(executor: str) -> list[dict]:
    """Non-terminal status entries for executor with a live pid."""
    out: list[dict] = []
    d = status_dir()
    if not d.is_dir():
        return out
    for path in d.glob("*.json"):
        try:
            entry = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if entry.get("executor") != executor:
            continue
        phase = entry.get("current_phase") or ""
        if is_terminal(phase):
            continue
        pid = int(entry.get("pid") or 0)
        if not _pid_alive(pid):
            continue
        out.append(entry)
    return out


def check_executor_available(executor: str, *, exclude_worker_id: str | None = None) -> tuple[bool, str]:
    """Return (ok, reason). ok=False means fail-fast busy."""
    if executor not in SERIALIZE_EXECUTORS:
        return True, ""

    holder = read_lock_holder(executor)
    if holder and holder.get("worker_id") != exclude_worker_id:
        return (
            False,
            f"{executor} busy (serialize Ornith): lock held by "
            f"worker={holder.get('worker_id')} pid={holder.get('pid')}",
        )

    actives = active_status_workers(executor)
    if exclude_worker_id:
        actives = [a for a in actives if a.get("worker_id") != exclude_worker_id]
    if actives:
        names = ", ".join(
            f"{a.get('worker_id')}(pid={a.get('pid')})" for a in actives[:5]
        )
        return False, f"{executor} busy (serialize Ornith): active workers: {names}"
    return True, ""


def acquire_leaf_lock(executor: str, worker_id: str, pid: int | None = None) -> tuple[bool, str]:
    """Write exclusive PID lock. Returns (ok, reason)."""
    if executor not in SERIALIZE_EXECUTORS:
        return True, ""

    ok, reason = check_executor_available(executor, exclude_worker_id=worker_id)
    if not ok:
        return False, reason

    locks_dir().mkdir(parents=True, exist_ok=True)
    path = lock_path_for(executor)
    payload = {
        "executor": executor,
        "worker_id": worker_id,
        "pid": int(pid or os.getpid()),
        "acquired_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    # Re-check after intending to write (tiny race window).
    holder = read_lock_holder(executor)
    if holder and holder.get("worker_id") != worker_id:
        return (
            False,
            f"{executor} busy (serialize Ornith): race lost to "
            f"worker={holder.get('worker_id')} pid={holder.get('pid')}",
        )
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return True, ""


def release_leaf_lock(executor: str, worker_id: str) -> None:
    if executor not in SERIALIZE_EXECUTORS:
        return
    path = lock_path_for(executor)
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if data.get("worker_id") == worker_id or int(data.get("pid") or 0) == os.getpid():
        try:
            path.unlink()
        except OSError:
            pass
