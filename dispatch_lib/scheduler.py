"""Dispatch-native utilization cycle orchestration."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from . import lane_health, outcomes
from .job_registry import contracts, validate_registry
from .utilization_policy import decide, denominator_source, provider_class, renewal_advisory
from .utilization_schema import SnapshotStore, make_idempotency_key


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _outcome_counts(executor: str) -> tuple[int, int, str]:
    rows = [row for row in outcomes._read() if row.get("executor") == executor]
    success = sum(row.get("result") == "success" for row in rows)
    last = rows[-1].get("result", "none") if rows else "none"
    return success, len(rows), last


def build_fleet_snapshots(matrix: dict[str, Any], availability_rows: dict[str, dict[str, Any]],
                          entitlements: dict[str, dict[str, Any]] | None = None,
                          now: float | None = None) -> list[dict[str, Any]]:
    """Classify every matrix executor exactly once into a utilization snapshot."""
    validate_registry()
    now = time.time() if now is None else now
    entitlements = entitlements or {}
    snapshots = []
    seen = set()
    for executor, cfg in matrix.get("executors", {}).items():
        if executor in seen:
            raise ValueError(f"duplicate executor: {executor}")
        seen.add(executor)
        availability = availability_rows.get(executor)
        entitlement = entitlements.get(executor, {})
        kind = provider_class(cfg, entitlement)
        account_evidence_required = kind != "local_capacity"
        evidence_fresh = availability is not None and entitlement.get(
            "evidence_fresh", not account_evidence_required
        )
        available = bool((availability or {}).get("available", False))
        cooldown = lane_health.in_cooldown(executor, now=now)
        success, observed, last_outcome = _outcome_counts(executor)
        numerator = entitlement.get("numerator", success if observed else int(available))
        denominator = entitlement.get("denominator", observed if observed else 1)
        denominator = denominator if isinstance(denominator, (int, float)) and denominator > 0 else 1
        value = float(numerator) / float(denominator)
        paid = bool(entitlement.get("paid", kind != "local_capacity" and cfg.get("provider") != "kilo-cli"))
        decision = decide(
            available=available,
            cooldown=cooldown,
            disabled=cfg.get("disabled") is True,
            evidence_fresh=evidence_fresh,
            utilization=value,
            paid=paid,
            exhausted=bool(entitlement.get("exhausted", False)),
        )
        window = {"kind": "rolling", "start": _iso(now - 86400), "end": _iso(now)}
        evidence_ids = list(entitlement.get("source_event_ids", []))
        key = make_idempotency_key(cfg.get("provider", executor), executor, window, evidence_ids)
        snapshot = {
            "schema_version": 1,
            "provider_id": cfg.get("provider", executor),
            "executor_id": executor,
            "provider_class": kind,
            "metric": {"numerator": numerator, "denominator": denominator, "value": value,
                       "unit": entitlement.get("unit", "successful_jobs_per_observed_jobs"), "window": window},
            "provenance": {"source_artifacts": entitlement.get("source_artifacts", ["dispatch_matrix", "availability", "lane_health", "outcomes"]),
                           "source_snapshot_ids": entitlement.get("source_snapshot_ids", []), "source_event_ids": evidence_ids},
            "confidence": entitlement.get("confidence", "high" if evidence_fresh else "low"),
            "observed_at": _iso(now), "freshness_at": _iso(now), "idempotency_key": key,
            "status": decision["status"], "recommendation": decision["recommendation"],
            "authority_source": "live_dispatch_state",
            "denominator_source": denominator_source(kind), "health_available": available,
            "cooldown": cooldown, "last_outcome": last_outcome,
            "exclusion_reason": decision["exclusion_reason"], "paid": paid,
            "renewal_advisory": "pending",
        }
        snapshot["renewal_advisory"] = renewal_advisory(snapshot, renewal_due=bool(entitlement.get("renewal_due")))
        snapshots.append(snapshot)
    extra = set(availability_rows) - seen
    if extra:
        raise ValueError(f"doctor/availability rows missing from matrix: {sorted(extra)}")
    return snapshots


def run_cycle(matrix: dict[str, Any], availability_rows: dict[str, dict[str, Any]],
              entitlements: dict[str, dict[str, Any]] | None = None,
              store: SnapshotStore | None = None, now: float | None = None,
              router=None) -> dict[str, Any]:
    snapshots = build_fleet_snapshots(matrix, availability_rows, entitlements, now)
    store = store or SnapshotStore()
    created = 0
    for snapshot in snapshots:
        _, was_created = store.write(snapshot)
        created += int(was_created)
    jobs = contracts()
    assignments = []
    if router is not None:
        for job in jobs:
            assignments.append({"job": job["name"], "executor": router(job["dispatch_brief"]), "status": "planned"})
    return {"snapshots": snapshots, "created": created, "replayed": len(snapshots) - created,
            "jobs": jobs, "assignments": assignments}
