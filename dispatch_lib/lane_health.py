"""Lane health: classify runtime failures and track per-executor cooldowns.

Cooldowns are persisted to lane_health.json (atomic tmp+rename). The router
treats an executor in active cooldown as unavailable. task-class failures are
NOT lane faults and never cause a demotion.
"""
import json
import os
import re
import time
from pathlib import Path

from .path_conventions import lane_health_path

# Backoff seconds per failure class.
BACKOFF = {"rate_limit": 60, "network": 120, "auth": 900}

_AUTH = re.compile(r"\b(401|403|unauthor|forbidden|invalid api key|token expired|expired)\b", re.I)
_RATE = re.compile(r"\b(429|rate.?limit|too many requests|quota)\b", re.I)
_NET = re.compile(r"\b(timed out|timeout|connection (refused|reset|error)|dns|unreachable|temporarily)\b", re.I)


def classify_failure(text: str) -> str:
    """Return one of: auth, rate_limit, network, task."""
    text = text or ""
    if _AUTH.search(text):
        return "auth"
    if _RATE.search(text):
        return "rate_limit"
    if _NET.search(text):
        return "network"
    return "task"


def _read() -> dict:
    path = lane_health_path()
    if not path.exists():
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _write_atomic(data: dict) -> None:
    path = lane_health_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def demote(executor: str, failure_class: str, now: float | None = None) -> None:
    """Record a cooldown for executor. No-op for task-class failures."""
    if failure_class == "task":
        return
    now = time.time() if now is None else now
    backoff = BACKOFF.get(failure_class, 120)
    data = _read()
    data[executor] = {
        "class": failure_class,
        "until": now + backoff,
        "since": now,
    }
    _write_atomic(data)


def in_cooldown(executor: str, now: float | None = None) -> bool:
    now = time.time() if now is None else now
    entry = _read().get(executor)
    if not entry:
        return False
    return now < float(entry.get("until", 0))


def recover(executor: str) -> None:
    data = _read()
    if executor in data:
        del data[executor]
        _write_atomic(data)


def needs_relogin() -> list:
    """Executors whose latest demotion was auth-class and still active."""
    now = time.time()
    out = []
    for ex, entry in _read().items():
        if entry.get("class") == "auth" and now < float(entry.get("until", 0)):
            out.append(ex)
    return out
