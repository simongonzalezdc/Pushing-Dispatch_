import os
import tempfile
import unittest
from unittest import mock

from dispatch_lib.job_registry import contracts, validate_registry
from dispatch_lib.scheduler import build_fleet_snapshots, run_cycle
from dispatch_lib.utilization_policy import renewal_advisory


MATRIX = {
    "executors": {
        "local": {"provider": "lm-studio"},
        "annual": {"provider": "openai-codex"},
        "quota": {"provider": "ollama-cloud", "disabled": True},
    }
}
AVAILABILITY = {
    "local": {"provider": "lm-studio", "available": True},
    "annual": {"provider": "openai-codex", "available": True},
    "quota": {"provider": "ollama-cloud", "available": False},
}


class TestUtilizationScheduler(unittest.TestCase):
    def test_classifies_every_executor_once_and_keeps_exclusions(self):
        with tempfile.TemporaryDirectory() as root, mock.patch.dict(os.environ, {"DISPATCH_ROOT": root}):
            rows = build_fleet_snapshots(MATRIX, AVAILABILITY, now=1_700_000_000)
        self.assertEqual({row["executor_id"] for row in rows}, set(MATRIX["executors"]))
        self.assertEqual(len(rows), len(MATRIX["executors"]))
        by_id = {row["executor_id"]: row for row in rows}
        self.assertEqual(by_id["local"]["provider_class"], "local_capacity")
        self.assertEqual(by_id["annual"]["provider_class"], "flat_rate_annual")
        self.assertEqual(by_id["annual"]["status"], "unknown")
        self.assertEqual(by_id["quota"]["exclusion_reason"], "matrix_disabled")

    def test_extra_doctor_row_fails_closed(self):
        rows = dict(AVAILABILITY)
        rows["ghost"] = {"provider": "unknown", "available": True}
        with tempfile.TemporaryDirectory() as root, mock.patch.dict(os.environ, {"DISPATCH_ROOT": root}):
            with self.assertRaisesRegex(ValueError, "missing from matrix"):
                build_fleet_snapshots(MATRIX, rows, now=1_700_000_000)

    def test_stale_and_exhausted_entitlements_fail_closed(self):
        evidence = {
            "annual": {"evidence_fresh": False, "paid": True},
            "quota": {"evidence_fresh": True, "paid": True, "exhausted": True},
        }
        with tempfile.TemporaryDirectory() as root, mock.patch.dict(os.environ, {"DISPATCH_ROOT": root}):
            rows = build_fleet_snapshots(MATRIX, AVAILABILITY, evidence, now=1_700_000_000)
        by_id = {row["executor_id"]: row for row in rows}
        self.assertEqual(by_id["annual"]["status"], "unknown")
        self.assertEqual(by_id["quota"]["status"], "excluded")
        self.assertNotEqual(by_id["annual"]["recommendation"], "schedule")

    def test_two_cycles_replay_without_double_counting(self):
        with tempfile.TemporaryDirectory() as root, mock.patch.dict(os.environ, {"DISPATCH_ROOT": root}):
            first = run_cycle(MATRIX, AVAILABILITY, now=1_700_000_000)
            second = run_cycle(MATRIX, AVAILABILITY, now=1_700_000_000)
        self.assertEqual(first["created"], 3)
        self.assertEqual(second["created"], 0)
        self.assertEqual(second["replayed"], 3)

    def test_job_assignments_use_the_dispatch_router_boundary(self):
        routed = []
        def router(brief):
            routed.append(brief)
            return "local"
        with tempfile.TemporaryDirectory() as root, mock.patch.dict(os.environ, {"DISPATCH_ROOT": root}):
            result = run_cycle(MATRIX, AVAILABILITY, now=1_700_000_000, router=router)
        self.assertEqual(len(result["assignments"]), 6)
        self.assertEqual(len(routed), 6)
        self.assertTrue(all(row["executor"] == "local" for row in result["assignments"]))

    def test_six_job_contracts_are_bounded_and_never_worker_retry(self):
        validate_registry()
        jobs = contracts()
        self.assertEqual(len(jobs), 6)
        self.assertTrue(all(job["retry_limit"] <= 2 for job in jobs))
        self.assertTrue(all(not job["worker_auto_retry"] for job in jobs))

    def test_renewal_policy_is_advisory_only(self):
        snapshot = {
            "provider_class": "flat_rate_annual",
            "status": "healthy_underused",
            "metric": {"value": 0.05},
        }
        self.assertEqual(renewal_advisory(snapshot, renewal_due=True), "consider_cancellation")
        self.assertFalse(hasattr(__import__("dispatch_lib.utilization_policy", fromlist=["x"]), "cancel"))


if __name__ == "__main__":
    unittest.main()
