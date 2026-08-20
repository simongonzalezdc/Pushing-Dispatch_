#!/usr/bin/env python3
"""smart_route — quota-aware, effort-aware tier router (CEO: "granular AND very
smart at routing the work to the right model at the right reasoning level").

Layer ON TOP of dispatch_matrix.toml auto_route: takes the tier's candidate
list, vetoes lanes by ledger state + policy (retired, forbidden, red), re-ranks
the survivors by the cost ladder (local > free > subscription > credits), picks
the winner, and logs an OpenRouter-style router-metadata row (decision, reason,
considered, vetoed) to route-log.jsonl.

Eval protocol (prior-art target 9 — LLMRouterBench warning): --baseline
always-cheap|always-strong|random registers the mandatory baselines. NO
quality claims until baselines run on outcomes data.

Usage:
  smart_route.py --tier standard [--task "text"] [--json]
  smart_route.py --tier hard_task --baseline always-cheap
"""
import argparse
import json
import os
import random
import re
import subprocess
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARE = os.path.expanduser("~/.local/share/pushing-dispatch")
STATE = os.path.join(SHARE, "ledger-state.json")
MATRIX = os.path.join(ROOT, "dispatch_matrix.toml")
ROUTELOG = os.path.join(SHARE, "route-log.jsonl")

COST_LADDER = {"local": 0, "free": 1, "subscription": 2, "credits": 3}
# Mirror of SUBSCRIPTIONS.yaml `retired:` — kept here so veto reasons are honest.
RETIRED_EXECUTORS = {
    "kimi-k3-ollama", "unsloth-nucbox", "ollama-xps-gpu", "agy-pro",
    "qwen35-35b-general", "qwen35-27b-review", "qwen36-35b-coding",
}
# Strong-model classes per matrix commentary (grok=kimi=deepseek-pro=agy head the
# hard/consult lists). Used only by the always-strong baseline and tie-breaks.
STRONG_HINTS = ("grok", "kimi", "deepseek-v4-pro", "agy", "terra", "sol")


def run_ledger_if_stale():
    if not os.path.exists(STATE):
        led = os.path.join(ROOT, "ops", "quota_ledger.py")
        subprocess.run([sys.executable, led, "status"], capture_output=True)


def load_state():
    try:
        return json.load(open(STATE))
    except Exception:
        return {"lanes": {}}


def matrix_candidates(tier):
    """Ordered candidate list for tier from dispatch_matrix.toml auto_route."""
    if not os.path.exists(MATRIX):
        return []
    key = "%s_candidates" % tier
    out, capture = [], False
    for line in open(MATRIX):
        m = re.match(r"^\s*(%s)\s*=\s*\[" % re.escape(key), line)
        if m:
            capture = True
            line = line[m.end() - 1:]
        if capture:
            out += re.findall(r'"([^"]+)"', line)
            if "]" in line and not line.strip().startswith("["):
                # handles both single-line and multi-line toml arrays
                if not line.rstrip().endswith(",") or line.rstrip().endswith("]"):
                    break
    # de-dupe preserving order
    seen, res = set(), []
    for c in out:
        if c not in seen:
            seen.add(c)
            res.append(c)
    return res


def lane_of(executor, state):
    for lane, row in (state.get("lanes") or {}).items():
        if executor in (row.get("executors") or []):
            return lane, row
    return None, None


def route(tier, task, baseline=None, json_out=False):
    run_ledger_if_stale()
    state = load_state()
    cands = matrix_candidates(tier)
    if not cands:
        sys.stderr.write("no candidates for tier %r in dispatch_matrix.toml\n" % tier)
        return 1

    considered, vetoed = [], []
    for ex in cands:
        lane, row = lane_of(ex, state)
        if ex in RETIRED_EXECUTORS:
            vetoed.append({"executor": ex, "reason": "retired lane (SUBSCRIPTIONS.yaml retired list — matrix drift)"})
            continue
        if lane is None:
            vetoed.append({"executor": ex, "reason": "unmapped lane (ledger blind spot)"})
            continue
        st = row.get("status")
        if st in ("RETIRED",):
            vetoed.append({"executor": ex, "reason": "retired lane %s" % lane})
        elif st in ("RED-RESET", "RED-HOLD"):
            vetoed.append({"executor": ex, "reason": "%s %s: %s" % (st, lane, row.get("detail", ""))})
        else:
            considered.append({"executor": ex, "lane": lane, "status": st, "kind": row.get("kind")})

    ts = datetime.now(timezone.utc).isoformat()
    if baseline == "always-cheap":
        pool = considered or [{"executor": c, "lane": "?", "kind": "subscription"} for c in cands[:1]]
        pick = min(pool, key=lambda c: COST_LADDER.get(c.get("kind"), 9))
    elif baseline == "always-strong":
        pool = considered or [{"executor": c} for c in cands]
        pick = next((c for c in pool if any(h in c["executor"] for h in STRONG_HINTS)), pool[0])
    elif baseline == "random":
        pool = considered or [{"executor": c} for c in cands]
        pick = random.choice(pool)
    else:
        if not considered:
            sys.stderr.write("ALL candidates vetoed for tier %r — no route (do not force; surface to operator)\n" % tier)
            meta = {"ts": ts, "tier": tier, "task": task, "decision": None,
                    "reason": "all candidates vetoed", "considered": considered, "vetoed": vetoed,
                    "baseline": baseline}
            with open(ROUTELOG, "a") as f:
                f.write(json.dumps(meta) + "\n")
            if json_out:
                print(json.dumps(meta, indent=1))
            else:
                print("NO ROUTE — %d candidates, all vetoed:" % len(vetoed))
                for v in vetoed:
                    print("  veto %s: %s" % (v["executor"], v["reason"]))
            return 2
        # cost ladder first; ties break to matrix order (which encodes effort preference)
        pick = min(considered, key=lambda c: (COST_LADDER.get(c.get("kind"), 9), considered.index(c)))

    meta = {"ts": ts, "tier": tier, "task": task, "decision": pick["executor"],
            "lane": pick.get("lane"), "kind": pick.get("kind"),
            "reason": "baseline=%s" % baseline if baseline else "cost-ladder re-rank of matrix order, quota-vetoed",
            "considered": considered, "vetoed": vetoed, "baseline": baseline}
    with open(ROUTELOG, "a") as f:
        f.write(json.dumps(meta) + "\n")

    if json_out:
        print(json.dumps(meta, indent=1))
    else:
        print("ROUTE %s -> %s (%s, %s)" % (tier, pick["executor"], pick.get("lane"), pick.get("kind")))
        print("  considered: %s" % ", ".join(c["executor"] for c in considered) or "(none)")
        for v in vetoed:
            print("  veto   %s: %s" % (v["executor"], v["reason"]))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tier", required=True,
                    help="matrix tier: trivial|standard|local_general|local_review|local_coding|hard_task|hard_breakout|long_context|consult")
    ap.add_argument("--task", default="")
    ap.add_argument("--baseline", choices=["always-cheap", "always-strong", "random"])
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    return route(a.tier, a.task, a.baseline, a.json)


if __name__ == "__main__":
    sys.exit(main())
