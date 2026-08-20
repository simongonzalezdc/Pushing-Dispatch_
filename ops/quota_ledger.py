#!/usr/bin/env python3
"""quota_ledger — the ownable piece (prior-art target 10: no standard exists).

Fuses SUBSCRIPTIONS.yaml (plan shape + window model) with observed signals
(quota-marks.jsonl, budget.jsonl, availability.json) into ledger-state.json:
one row per lane: status, class, eta, evidence. Statuses:
  GREEN        usable now
  AMBER        usable but low balance / degrading / unexplained availability flip
  RED-RESET    quota dead with a computable reset (weekly pool, calendar, rolling)
  RED-HOLD     dead with NO predictable reset (fair-use lockout, payment-dead)
  RETIRED      never route
Purchase paths are structurally absent — never-pay law (CEO 2026-08-20).

Usage: quota_ledger.py [status|json]   (default: status)
Deps: PyYAML if installed; else falls back to the JSON twin ledger-state builds.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARE = os.path.expanduser("~/.local/share/pushing-dispatch")
SUBS = os.path.join(ROOT, "SUBSCRIPTIONS.yaml")
MARKS = os.path.join(SHARE, "quota-marks.jsonl")
BUDGET = os.path.join(SHARE, "budget.jsonl")
AVAIL = os.path.join(SHARE, "availability.json")
STATE = os.path.join(SHARE, "ledger-state.json")

NOW = datetime.now(timezone.utc)


def load_marks():
    rows = []
    if os.path.exists(MARKS):
        for line in open(MARKS):
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return rows


def last_mark(marks, lane, kind):
    best, best_ts = None, None
    for m in marks:
        if m.get("lane") == lane and m.get("event") == kind:
            ts = m.get("ts", "")
            if best_ts is None or ts >= best_ts:
                best, best_ts = m, ts
    return best


def parse_ts(s):
    try:
        t = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if t.tzinfo is None:  # date-only strings parse naive — pin to UTC
            t = t.replace(tzinfo=timezone.utc)
        return t
    except Exception:
        return None


def load_subs():
    try:
        import yaml  # type: ignore
        with open(SUBS) as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        sys.stderr.write("PyYAML missing — install or maintain ledger-state.json manually\n")
        raise SystemExit(2)


def lane_status(name, lane, marks):
    """Returns (status, detail) using the window model + observed marks."""
    if lane.get("policy") == "dead" or name == "retired":
        return "RETIRED", "policy-dead"
    w = lane.get("window", {}) or {}
    model = w.get("model", "none")

    death = last_mark(marks, name, "observed_death")
    recovery = last_mark(marks, name, "observed_recovery")

    # a later recovery clears an earlier death for timed classes
    death_ts = parse_ts(death["ts"]) if death else None
    rec_ts = parse_ts(recovery["ts"]) if recovery else None

    if model == "none":
        return "GREEN", "hardware/policy lane"

    if model == "fair_use":
        if death and (not rec_ts or rec_ts < (death_ts or NOW)):
            return "RED-HOLD", "fair-use enforcement; NO predictable reset — route away, cool down, do not retry-burst"
        return "GREEN", "fair-use plan; watch burst patterns"

    if model == "weekly_pool":
        if death and (not rec_ts or rec_ts < (death_ts or NOW)):
            base = parse_ts(w.get("last_observed_death", "")) or death_ts or NOW
            eta = base + timedelta(days=float(w.get("period_days", 7)))
            # honest floor: we know the pool resets weekly, not the exact stamp
            return ("RED-RESET", "weekly pool; eta %s (Settings>Usage shows exact stamp)" % eta.date().isoformat())
        return "GREEN", "weekly pool active"

    if model == "calendar_monthly":
        nr = w.get("next_renewal") or w.get("last_reset")
        t = parse_ts(nr) if nr else None
        if t and t > NOW:
            return "GREEN", "renews %s" % t.date().isoformat()
        if w.get("observed") == "never-exhausted":
            return "GREEN", "never observed exhausted"
        return "GREEN", "calendar plan"

    if model in ("balance", "dual_bucket"):
        if model == "dual_bucket":
            bal = float(w.get("personal", 0)) + float(w.get("bonus", 0))
            floor = float(w.get("floor", 0)) * 2  # personal floor governs; bonus is soft
        else:
            key = "balance_usd" if "balance_usd" in w else "balance_credits"
            bal = float(w.get(key, 0))
            floor = float(w.get("floor", 0))
        # marks can refresh balances
        bm = last_mark(marks, name, "balance_read")
        if bm and "value" in bm:
            bal = float(bm["value"])
        if bal <= floor:
            return "RED-HOLD", "balance %.2f at/below floor %.2f (no purchase path — never-pay law)" % (bal, floor)
        if bal <= floor * 2:
            return "AMBER", "balance %.2f approaching floor %.2f" % (bal, floor)
        return "GREEN", "balance %.2f" % bal

    if model == "rolling":
        if death and (not rec_ts or rec_ts < (death_ts or NOW)):
            eta = w.get("eta_recovery")
            t = parse_ts(eta) if eta else ((death_ts or NOW) + timedelta(hours=24))
            if t > NOW:
                return "RED-RESET", "rolling window; eta %s" % t.isoformat()
        return "GREEN", "rolling window"

    return "GREEN", "unmodeled — treat as green until observed otherwise"


def executor_map(subs):
    ex2lane = {}
    for lane, cfg in (subs.get("lanes") or {}).items():
        for ex in cfg.get("executors", []) or []:
            ex2lane[ex] = lane
    return ex2lane


def availability_conflicts(subs, rows):
    """availability.json DOWN + ledger GREEN => AMBER-unexplained (unknown != dead)."""
    conflicts = []
    try:
        av = json.load(open(AVAIL))
    except Exception:
        return conflicts
    ex2lane = executor_map(subs)
    for ex, st in (av.get("executors") or {}).items():
        lane = ex2lane.get(ex)
        if not lane:
            continue
        if st.get("available") is False and rows.get(lane, {}).get("status") == "GREEN":
            conflicts.append((lane, ex))
    return conflicts


def main():
    subs = load_subs()
    marks = load_marks()
    rows = {}
    for name, lane in (subs.get("lanes") or {}).items():
        status, detail = lane_status(name, lane, marks)
        rows[name] = {
            "status": status,
            "kind": lane.get("kind"),
            "window_model": (lane.get("window") or {}).get("model"),
            "detail": detail,
            "executors": lane.get("executors", []),
            "policy": lane.get("policy"),
        }
    for lane, ex in availability_conflicts(subs, rows):
        rows[lane]["status"] = "AMBER"
        rows[lane]["detail"] += " | availability says DOWN for %s (unexplained)" % ex

    state = {"generated_utc": NOW.isoformat(), "lanes": rows,
             "law": "purchase paths forbidden — never-pay (CEO 2026-08-20)"}
    os.makedirs(SHARE, exist_ok=True)
    with open(STATE, "w") as f:
        json.dump(state, f, indent=1)

    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "json":
        print(json.dumps(state, indent=1))
        return 0
    order = {"GREEN": 0, "AMBER": 1, "RED-RESET": 2, "RED-HOLD": 3, "RETIRED": 4}
    print("quota ledger @ %s" % NOW.strftime("%Y-%m-%dT%H:%MZ"))
    for name, r in sorted(rows.items(), key=lambda kv: (order.get(kv[1]["status"], 9), kv[0])):
        print("  %-13s %-9s %s" % (name, r["status"], r["detail"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
