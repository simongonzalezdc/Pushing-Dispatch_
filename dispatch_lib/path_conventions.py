"""
Path conventions for pushing-dispatch artifacts.

All dispatch artifacts (status files, logs, budget ledger) live under
DISPATCH_ROOT. Default: ~/.local/share/pushing-dispatch/
Override via DISPATCH_ROOT env var.
"""

import os
from pathlib import Path


def dispatch_root() -> Path:
    """Return the root directory for dispatch artifacts."""
    return Path(os.environ.get("DISPATCH_ROOT", os.path.expanduser("~/.local/share/pushing-dispatch")))


def status_dir() -> Path:
    return dispatch_root() / "status"


def log_dir() -> Path:
    return dispatch_root() / "logs"


def budget_path() -> Path:
    return dispatch_root() / "budget.jsonl"


def registry_path() -> Path:
    return dispatch_root() / "session_registry.jsonl"


def status_path(worker_id: str) -> Path:
    return status_dir() / f"{worker_id}.json"


def log_path(worker_id: str) -> Path:
    return log_dir() / f"{worker_id}.log"


def question_dir() -> Path:
    return dispatch_root() / "questions"


def question_path(worker_id: str) -> Path:
    return question_dir() / f"{worker_id}.md"


def ensure_dirs():
    """Create all required directories."""
    for d in [status_dir(), log_dir(), question_dir()]:
        d.mkdir(parents=True, exist_ok=True)
