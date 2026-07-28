import copy
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from dispatch_lib.telemetry_export import render_html
from dispatch_lib.utilization_schema import (
    SnapshotStore,
    SnapshotValidationError,
    make_idempotency_key,
    validate_snapshot,
)


def example_snapshot():
    window = {
        "kind": "rolling",
        "start": "2026-07-17T00:00:00Z",
        "end": "2026-07-17T23:59:59Z",
    }
    event_ids = ["outcome-1", "health-1"]
    return {
        "schema_version": 1,
        "provider_id": "nucbox",
        "executor_id": "lm-studio",
        "provider_class": "local_capacity",
        "metric": {
            "numerator": 3,
            "denominator": 4,
            "value": 0.75,
            "unit": "healthy_windows_per_observed_windows",
            "window": window,
        },
        "provenance": {
            "source_artifacts": ["availability", "lane_health", "outcomes"],
            "source_snapshot_ids": ["availability-1"],
            "source_event_ids": event_ids,
        },
        "confidence": "high",
        "observed_at": "2026-07-17T21:00:00Z",
        "freshness_at": "2026-07-17T21:05:00Z",
        "idempotency_key": make_idempotency_key("nucbox", "lm-studio", window, event_ids),
        "status": "healthy",
        "recommendation": "schedule",
        "authority_source": "live_dispatch_state",
    }


class TestUtilizationControlPlane(unittest.TestCase):
    def test_one_executor_snapshot_replay_and_html_journey(self):
        with tempfile.TemporaryDirectory() as root:
            with mock.patch.dict(os.environ, {"DISPATCH_ROOT": root}):
                snapshot = example_snapshot()
                store = SnapshotStore()
                path, created = store.write(snapshot)
                self.assertTrue(created)
                replay_path, replay_created = store.write(snapshot)
                self.assertEqual(path, replay_path)
                self.assertFalse(replay_created)
                self.assertEqual(store.read(snapshot["idempotency_key"]), snapshot)

                output = Path(root) / "reports" / "utilization.html"
                render_html([snapshot], output)
                rendered = output.read_text(encoding="utf-8")
                self.assertIn("lm-studio", rendered)
                self.assertIn("75.0%", rendered)
                self.assertIn("schedule", rendered)

                self.assertFalse((Path(root) / "availability.json").exists())
                self.assertFalse((Path(root) / "lane_health.json").exists())

                render_html([snapshot], output, [{"job": "snapshot_generation", "executor": "lm-studio", "status": "planned"}])
                rendered = output.read_text(encoding="utf-8")
                self.assertIn("Recurring work plan", rendered)
                self.assertIn("snapshot_generation", rendered)

    def test_same_key_with_different_evidence_fails_closed(self):
        with tempfile.TemporaryDirectory() as root:
            with mock.patch.dict(os.environ, {"DISPATCH_ROOT": root}):
                snapshot = example_snapshot()
                SnapshotStore().write(snapshot)
                changed = copy.deepcopy(snapshot)
                changed["recommendation"] = "reserve"
                with self.assertRaises(SnapshotValidationError):
                    SnapshotStore().write(changed)

    def test_schema_rejects_invalid_denominator_and_authority(self):
        snapshot = example_snapshot()
        snapshot["metric"]["denominator"] = 0
        with self.assertRaises(SnapshotValidationError):
            validate_snapshot(snapshot)
        snapshot = example_snapshot()
        snapshot["authority_source"] = "html_renderer"
        with self.assertRaises(SnapshotValidationError):
            validate_snapshot(snapshot)

    def test_renderer_escapes_untrusted_labels(self):
        with tempfile.TemporaryDirectory() as root:
            snapshot = example_snapshot()
            snapshot["recommendation"] = "<script>alert(1)</script>"
            output = Path(root) / "report.html"
            render_html([snapshot], output)
            rendered = output.read_text(encoding="utf-8")
            self.assertNotIn("<script>alert(1)</script>", rendered)
            self.assertIn("&lt;script&gt;", rendered)

    def test_corrupt_snapshot_fails_closed(self):
        with tempfile.TemporaryDirectory() as root:
            with mock.patch.dict(os.environ, {"DISPATCH_ROOT": root}):
                snapshot = example_snapshot()
                path, _ = SnapshotStore().write(snapshot)
                path.write_text("{not-json", encoding="utf-8")
                with self.assertRaises(ValueError):
                    SnapshotStore().read(snapshot["idempotency_key"])

    def test_renderer_failure_preserves_previous_artifact(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / "report.html"
            output.write_text("previous-good-artifact", encoding="utf-8")
            with mock.patch("dispatch_lib.telemetry_export.os.replace", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    render_html([example_snapshot()], output)
            self.assertEqual(output.read_text(encoding="utf-8"), "previous-good-artifact")
            self.assertEqual(list(Path(root).glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
