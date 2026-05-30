"""Append-only outcome ledger. Substrate for the (off-by-default) learning loop.

Each dispatch records its executor, tier, result class, duration, and cost.
The router can later bias candidate ordering from this history when
[auto_route].learning is enabled.
"""
import json
import os
import time

from .path_conventions import outcomes_path


def record(worker_id, executor, tier, result, duration_s, cost_usd):
    """Append one outcome. result in {success, auth, rate_limit, network, task}."""
    path = outcomes_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": time.time(),
        "worker_id": worker_id,
        "executor": executor,
        "tier": tier,
        "result": result,
        "duration_s": duration_s,
        "cost_usd": cost_usd,
    }
    with open(path, "a") as f:
        f.write(json.dumps(entry) + "\n")
        f.flush()
        os.fsync(f.fileno())


def _read():
    path = outcomes_path()
    if not path.exists():
        return []
    out = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return out


def success_rate(executor):
    rows = [r for r in _read() if r["executor"] == executor]
    if not rows:
        return None
    ok = sum(1 for r in rows if r["result"] == "success")
    return ok / len(rows)
