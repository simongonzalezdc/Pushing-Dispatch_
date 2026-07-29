"""Tests for Ornith / unsloth-nucbox serialize fail-fast."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from dispatch_lib import leaf_serialize


class LeafSerializeTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._env = mock.patch.dict(os.environ, {"DISPATCH_ROOT": str(self.root)})
        self._env.start()
        (self.root / "status").mkdir()
        (self.root / "locks").mkdir()

    def tearDown(self):
        self._env.stop()
        self._tmp.cleanup()

    def test_non_serialized_executor_always_ok(self):
        ok, reason = leaf_serialize.check_executor_available("zai-glm")
        self.assertTrue(ok)
        self.assertEqual(reason, "")

    def test_busy_when_lock_held_by_live_pid(self):
        lock = leaf_serialize.lock_path_for("unsloth-nucbox")
        lock.write_text(
            json.dumps(
                {
                    "executor": "unsloth-nucbox",
                    "worker_id": "w-holder",
                    "pid": os.getpid(),
                }
            )
        )
        ok, reason = leaf_serialize.check_executor_available("unsloth-nucbox")
        self.assertFalse(ok)
        self.assertIn("w-holder", reason)

    def test_stale_lock_ignored(self):
        lock = leaf_serialize.lock_path_for("unsloth-nucbox")
        lock.write_text(
            json.dumps(
                {
                    "executor": "unsloth-nucbox",
                    "worker_id": "w-dead",
                    "pid": 99999999,
                }
            )
        )
        ok, reason = leaf_serialize.check_executor_available("unsloth-nucbox")
        self.assertTrue(ok, reason)

    def test_acquire_and_release(self):
        ok, reason = leaf_serialize.acquire_leaf_lock(
            "unsloth-nucbox", "w-new", pid=os.getpid()
        )
        self.assertTrue(ok, reason)
        ok2, reason2 = leaf_serialize.check_executor_available(
            "unsloth-nucbox", exclude_worker_id="w-new"
        )
        # Same worker excluded → free for self-check; other worker sees busy.
        ok3, reason3 = leaf_serialize.check_executor_available("unsloth-nucbox")
        self.assertFalse(ok3)
        self.assertIn("w-new", reason3)
        leaf_serialize.release_leaf_lock("unsloth-nucbox", "w-new")
        ok4, _ = leaf_serialize.check_executor_available("unsloth-nucbox")
        self.assertTrue(ok4)

    def test_active_status_worker_blocks(self):
        status = self.root / "status" / "w-active.json"
        status.write_text(
            json.dumps(
                {
                    "worker_id": "w-active",
                    "executor": "unsloth-nucbox",
                    "current_phase": "starting",
                    "pid": os.getpid(),
                }
            )
        )
        ok, reason = leaf_serialize.check_executor_available("unsloth-nucbox")
        self.assertFalse(ok)
        self.assertIn("w-active", reason)


if __name__ == "__main__":
    unittest.main()
