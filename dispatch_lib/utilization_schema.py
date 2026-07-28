"""Versioned utilization snapshots for the Dispatch control plane."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .path_conventions import utilization_snapshot_path

SCHEMA_VERSION = 1
PROVIDER_CLASSES = {
    "flat_rate_annual",
    "quota_entitlement",
    "credit_balance",
    "usage_metered",
    "local_capacity",
}
CONFIDENCE_LEVELS = {"low", "medium", "high"}
REQUIRED_FIELDS = {
    "schema_version",
    "provider_id",
    "executor_id",
    "provider_class",
    "metric",
    "provenance",
    "confidence",
    "observed_at",
    "freshness_at",
    "idempotency_key",
    "status",
    "recommendation",
    "authority_source",
}
REQUIRED_METRIC_FIELDS = {"numerator", "denominator", "value", "unit", "window"}


class SnapshotValidationError(ValueError):
    """Raised when a utilization snapshot violates the public contract."""


def make_idempotency_key(
    provider_id: str,
    executor_id: str,
    window: dict[str, Any],
    source_event_ids: list[str] | None = None,
) -> str:
    """Return a stable key for one provider/executor/window evidence set."""
    material = {
        "provider_id": provider_id,
        "executor_id": executor_id,
        "window": window,
        "source_event_ids": sorted(source_event_ids or []),
    }
    digest = hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return f"utilization-{digest[:32]}"


def validate_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Validate and return a v1 snapshot without mutating it."""
    missing = REQUIRED_FIELDS - snapshot.keys()
    if missing:
        raise SnapshotValidationError(f"missing fields: {sorted(missing)}")
    if snapshot["schema_version"] != SCHEMA_VERSION:
        raise SnapshotValidationError("unsupported schema_version")
    if snapshot["provider_class"] not in PROVIDER_CLASSES:
        raise SnapshotValidationError("unknown provider_class")
    if snapshot["confidence"] not in CONFIDENCE_LEVELS:
        raise SnapshotValidationError("unknown confidence")
    if snapshot["authority_source"] != "live_dispatch_state":
        raise SnapshotValidationError("authority_source must be live_dispatch_state")
    if not isinstance(snapshot["metric"], dict):
        raise SnapshotValidationError("metric must be an object")
    metric_missing = REQUIRED_METRIC_FIELDS - snapshot["metric"].keys()
    if metric_missing:
        raise SnapshotValidationError(f"missing metric fields: {sorted(metric_missing)}")
    numerator = snapshot["metric"]["numerator"]
    denominator = snapshot["metric"]["denominator"]
    if not isinstance(numerator, (int, float)) or isinstance(numerator, bool):
        raise SnapshotValidationError("metric numerator must be numeric")
    if not isinstance(denominator, (int, float)) or isinstance(denominator, bool):
        raise SnapshotValidationError("metric denominator must be numeric")
    if denominator <= 0:
        raise SnapshotValidationError("metric denominator must be positive")
    expected = numerator / denominator
    if abs(float(snapshot["metric"]["value"]) - expected) > 1e-9:
        raise SnapshotValidationError("metric value must equal numerator / denominator")
    provenance = snapshot["provenance"]
    if not isinstance(provenance, dict) or not provenance.get("source_artifacts"):
        raise SnapshotValidationError("provenance.source_artifacts is required")
    if not str(snapshot["idempotency_key"]).startswith("utilization-"):
        raise SnapshotValidationError("invalid idempotency_key")
    return snapshot


class SnapshotStore:
    """Atomic, replay-safe storage for validated snapshots."""

    def write(self, snapshot: dict[str, Any]) -> tuple[Path, bool]:
        validate_snapshot(snapshot)
        path = utilization_snapshot_path(snapshot["idempotency_key"])
        path.parent.mkdir(parents=True, exist_ok=True)
        encoded = json.dumps(snapshot, indent=2, sort_keys=True) + "\n"
        if path.exists():
            existing = path.read_text(encoding="utf-8")
            if existing != encoded:
                raise SnapshotValidationError(
                    "idempotency key already exists with different evidence"
                )
            return path, False
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        return path, True

    def read(self, idempotency_key: str) -> dict[str, Any] | None:
        path = utilization_snapshot_path(idempotency_key)
        if not path.exists():
            return None
        snapshot = json.loads(path.read_text(encoding="utf-8"))
        return validate_snapshot(snapshot)
