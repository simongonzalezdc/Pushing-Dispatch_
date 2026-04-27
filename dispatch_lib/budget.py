"""
Budget tracking for dispatch workers.

Append-only JSONL ledger. Each entry records one worker's cost
for a single session. Supports tree rollup via parent_id.
"""

import json
import time
from datetime import date
from pathlib import Path

from .path_conventions import budget_path, dispatch_root


def record_spend(
    worker_id: str,
    provider: str,
    cost: float,
    currency: str = "USD",
    parent_id: str = None,
    tokens_in: int = 0,
    tokens_out: int = 0,
):
    """Append a spend record to the budget ledger."""
    path = budget_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "date": date.today().isoformat(),
        "worker_id": worker_id,
        "provider": provider,
        "cost": cost,
        "currency": currency,
        "parent_id": parent_id,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
    }
    with open(path, "a") as f:
        f.write(json.dumps(entry) + "\n")


def today_total(currency: str = "USD") -> float:
    """Sum all spend for today."""
    today = date.today().isoformat()
    total = 0.0
    for entry in _read_ledger():
        if entry.get("date") == today and entry.get("currency", "USD") == currency:
            total += entry.get("cost", 0.0)
    return total


def tree_breakdown_today() -> dict:
    """Group today's spend by root worker (tree view).

    Returns: {root_worker_id: {"workers": [...], "total": float}}
    """
    today = date.today().isoformat()
    entries = [e for e in _read_ledger() if e.get("date") == today]

    # Build parent map
    parent_map = {}
    for e in entries:
        wid = e["worker_id"]
        pid = e.get("parent_id")
        if pid:
            parent_map[wid] = pid

    def find_root(wid):
        seen = set()
        while wid in parent_map and wid not in seen:
            seen.add(wid)
            wid = parent_map[wid]
        return wid

    trees = {}
    for e in entries:
        root = find_root(e["worker_id"])
        if root not in trees:
            trees[root] = {"workers": [], "total": 0.0}
        trees[root]["workers"].append(e)
        trees[root]["total"] += e.get("cost", 0.0)

    return trees


def _read_ledger() -> list[dict]:
    """Read all ledger entries."""
    path = budget_path()
    if not path.exists():
        return []
    entries = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries
