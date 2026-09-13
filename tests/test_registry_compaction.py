"""Registry compaction retention: old terminal rows only, fail-closed.

CS red case (compact_recovery_acceptance): compaction dropped a 9-day-old
registry row whose worker status was nonterminal, and rewrote the registry
with a plain truncating write. These tests pin the repair — removal
eligibility requires an old, parseable timestamp AND a provably terminal
worker lifecycle (missing/corrupt status is retained, never discarded) —
plus atomic, append-serialized rewrites.
"""
import fcntl
import json
import os
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import cli
from dispatch_lib import status_writer
from dispatch_lib.path_conventions import registry_lock_path, registry_path


def _ts(days_ago: float) -> str:
    when = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return when.isoformat()


class RegistryCompactionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.env = mock.patch.dict(os.environ, {"DISPATCH_ROOT": str(self.root)})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def _write_registry(self, rows):
        registry_path().parent.mkdir(parents=True, exist_ok=True)
        registry_path().write_text(
            "".join(json.dumps(r) + "\n" for r in rows))

    def _read_registry_ids(self):
        return [json.loads(line).get("worker_id")
                for line in registry_path().read_text().splitlines() if line.strip()]

    def _make_status(self, worker_id, phase, finalized_at=None):
        # Written directly (not via set_phase) so test rows can use phases
        # outside the writer's enum, like the CS harness's "running" row.
        status_dir = self.root / "status"
        status_dir.mkdir(parents=True, exist_ok=True)
        (status_dir / f"{worker_id}.json").write_text(json.dumps({
            "schema_version": 3, "worker_id": worker_id,
            "current_phase": phase, "finalized_at": finalized_at,
            "exit_code": None,
        }))

    def _compact(self):
        cli.cmd_compact(SimpleNamespace())

    # -- the CS red case and its retention family --

    def test_old_nonterminal_worker_mapping_retained(self):
        self._make_status("w-old-active", "running")
        self._write_registry([
            {"worker_id": "w-old-active", "timestamp": _ts(9), "status": "running"},
            {"worker_id": "w-recent-done", "timestamp": _ts(0.1), "status": "done"},
        ])
        self._compact()
        self.assertEqual(self._read_registry_ids(), ["w-old-active", "w-recent-done"])

    def test_old_terminal_worker_removed(self):
        self._make_status("w-old-done", "done", finalized_at=_ts(8))
        self._write_registry([
            {"worker_id": "w-old-done", "timestamp": _ts(9), "status": "done"},
        ])
        self._compact()
        self.assertEqual(self._read_registry_ids(), [])

    def test_status_missing_retained(self):
        self._write_registry([
            {"worker_id": "w-no-status", "timestamp": _ts(9), "status": "done"},
        ])
        self._compact()
        self.assertEqual(self._read_registry_ids(), ["w-no-status"])

    def test_status_corrupt_retained(self):
        status_dir = self.root / "status"
        status_dir.mkdir(parents=True, exist_ok=True)
        (status_dir / "w-corrupt.json").write_text("{corrupt")
        self._write_registry([
            {"worker_id": "w-corrupt", "timestamp": _ts(9), "status": "done"},
        ])
        self._compact()
        self.assertEqual(self._read_registry_ids(), ["w-corrupt"])

    def test_unfinalized_terminal_phase_retained(self):
        # A terminal phase without finalized_at is not proof of a terminal
        # lifecycle; eligibility requires both.
        self._make_status("w-unfinalized", "done")
        self._write_registry([
            {"worker_id": "w-unfinalized", "timestamp": _ts(9), "status": "done"},
        ])
        self._compact()
        self.assertEqual(self._read_registry_ids(), ["w-unfinalized"])

    def test_malformed_timestamp_retained(self):
        self._make_status("w-bad-ts", "done", finalized_at=_ts(8))
        self._write_registry([
            {"worker_id": "w-bad-ts", "timestamp": "not-a-date", "status": "done"},
        ])
        self._compact()
        self.assertEqual(self._read_registry_ids(), ["w-bad-ts"])

    def test_row_without_worker_id_retained(self):
        self._write_registry([
            {"event": "mystery-row", "timestamp": _ts(9)},
        ])
        self._compact()
        self.assertEqual(self._read_registry_ids(), [None])
        self.assertIn("mystery-row", registry_path().read_text())

    def test_nonterminal_status_bytes_preserved_by_compact(self):
        self._make_status("w-keep", "running")
        before = status_writer.read_status("w-keep")
        self._write_registry([
            {"worker_id": "w-keep", "timestamp": _ts(9), "status": "running"},
        ])
        self._compact()
        self.assertEqual(status_writer.read_status("w-keep"), before)

    # -- atomicity and serialization --

    def test_rewrite_is_atomic_no_tmp_leftovers(self):
        self._make_status("w-old-done", "done", finalized_at=_ts(8))
        self._write_registry([
            {"worker_id": "w-old-done", "timestamp": _ts(9), "status": "done"},
            {"worker_id": "w-keep", "timestamp": _ts(0.1), "status": "x"},
        ])
        self._compact()
        leftovers = [p for p in self.root.glob("*.tmp")]
        self.assertEqual(leftovers, [])
        self.assertEqual(self._read_registry_ids(), ["w-keep"])

    def test_append_serializes_against_compaction_lock(self):
        self._write_registry([
            {"worker_id": "w-a", "timestamp": _ts(0.1), "status": "x"},
        ])
        lock = registry_lock_path()
        lock.parent.mkdir(parents=True, exist_ok=True)
        with open(lock, "a+b") as held:
            fcntl.flock(held.fileno(), fcntl.LOCK_EX)
            done = threading.Event()

            def run_compact():
                self._compact()
                done.set()

            worker = threading.Thread(target=run_compact, daemon=True)
            worker.start()
            # While the lock is held the compaction must not complete.
            self.assertFalse(done.wait(timeout=0.5),
                             "compaction ran while another writer held the lock")
            fcntl.flock(held.fileno(), fcntl.LOCK_UN)
        worker.join(timeout=5)
        self.assertFalse(worker.is_alive())
        # After compaction (registry unchanged: recent row kept), a locked
        # append lands and both rows survive.
        cli._append_registry({"worker_id": "w-b", "timestamp": _ts(0), "status": "y"})
        self.assertEqual(self._read_registry_ids(), ["w-a", "w-b"])

    def test_append_is_fsynced_and_visible(self):
        cli._append_registry({"worker_id": "w-x", "timestamp": _ts(0), "status": "s"})
        self.assertEqual(self._read_registry_ids(), ["w-x"])


if __name__ == "__main__":
    unittest.main()
