import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from dispatch_lib import cwd_lock, outcomes


class TestCwdLock(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.status_dir = self.root / "status"
        self.status_dir.mkdir()
        # Patch BOTH surfaces: cwd_lock's lock dir and status_writer's
        # status_path (read_status resolves through the latter).
        p1 = mock.patch("dispatch_lib.cwd_lock.dispatch_root", return_value=self.root)
        p2 = mock.patch("dispatch_lib.status_writer.status_path",
                        side_effect=lambda wid=self.status_dir: self.status_dir / f"{wid}.json")
        p1.start(); p2.start()
        self.addCleanup(p1.stop); self.addCleanup(p2.stop)
        self.addCleanup(self.tmp.cleanup)

    def _mk_status(self, wid, phase):
        (self.status_dir / f"{wid}.json").write_text(json.dumps(
            {"worker_id": wid, "current_phase": phase}))

    def test_acquire_and_release(self):
        ok, holder = cwd_lock.acquire("w-1", "/repo/a")
        self.assertTrue(ok); self.assertIsNone(holder)
        ok2, holder2 = cwd_lock.acquire("w-1", "/repo/a")  # re-entrant by same worker
        self.assertTrue(ok2)
        cwd_lock.release("w-1")
        ok3, _ = cwd_lock.acquire("w-2", "/repo/a")
        self.assertTrue(ok3)

    def test_conflict_blocks(self):
        self._mk_status("w-1", "running")
        ok, holder = cwd_lock.acquire("w-1", "/repo/a")
        self.assertTrue(ok)
        ok2, holder2 = cwd_lock.acquire("w-2", "/repo/a")
        self.assertFalse(ok2)
        self.assertEqual(holder2["worker_id"], "w-1")

    def test_terminal_holder_is_stale(self):
        self._mk_status("w-1", "done")
        ok, _ = cwd_lock.acquire("w-1", "/repo/a")
        self.assertTrue(ok)
        ok2, _ = cwd_lock.acquire("w-2", "/repo/a")
        self.assertTrue(ok2)  # stale lock stolen

    def test_missing_status_is_stale(self):
        ok, _ = cwd_lock.acquire("w-ghost", "/repo/a")
        self.assertTrue(ok)
        ok2, _ = cwd_lock.acquire("w-2", "/repo/a")
        self.assertTrue(ok2)


class TestErrorRate30d(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "outcomes.jsonl"
        p = mock.patch("dispatch_lib.outcomes.outcomes_path", return_value=self.path)
        p.start(); self.addCleanup(p.stop); self.addCleanup(self.tmp.cleanup)

    def test_min_samples_guard(self):
        for i in range(3):
            outcomes.record(f"w{i}", "grok-build", "t", "auth", 1, 0)
        rate, n = outcomes.error_rate_30d("grok-build", min_samples=5)
        self.assertIsNone(rate); self.assertEqual(n, 3)

    def test_rate_computation(self):
        for i in range(6):
            outcomes.record(f"w{i}", "unsloth-nucbox", "t",
                            "success" if i < 2 else "task", 1, 0)
        rate, n = outcomes.error_rate_30d("unsloth-nucbox", min_samples=5)
        self.assertAlmostEqual(rate, 4 / 6); self.assertEqual(n, 6)

    def test_cost_basis_recorded(self):
        outcomes.record("w9", "zai-glm", "t", "success", 12.5, 0.0)
        entry = json.loads(self.path.read_text().strip().splitlines()[-1])
        self.assertEqual(entry["cost_basis"], "unpriced")
        self.assertEqual(entry["duration_s"], 12.5)


if __name__ == "__main__":
    unittest.main()
