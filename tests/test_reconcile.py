import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import cli
from dispatch_lib.path_conventions import registry_path, status_path
from dispatch_lib.reconcile import orphaned_reason, process_state
from dispatch_lib.status_writer import init_status, read_status


class ReconcileClassificationTests(unittest.TestCase):
    def _status(self, **changes):
        status = {
            "worker_id": "w-test",
            "current_phase": "starting",
            "pid": 424242,
            "finalized_at": None,
        }
        status.update(changes)
        return status

    def test_absent_nonterminal_process_is_candidate(self):
        reason = orphaned_reason(self._status(), probe=lambda _pid: "absent")
        self.assertEqual(reason, "recorded process is absent")

    def test_live_or_unknown_process_fails_closed(self):
        for state in ("alive", "unknown"):
            with self.subTest(state=state):
                self.assertIsNone(
                    orphaned_reason(
                        self._status(), probe=lambda _pid, value=state: value
                    )
                )

    def test_terminal_checkpoint_and_finalized_rows_are_preserved(self):
        for status in (
            self._status(current_phase="done"),
            self._status(current_phase="awaiting_checkpoint", finalized_at="now"),
            self._status(finalized_at="now"),
        ):
            with self.subTest(status=status):
                self.assertIsNone(orphaned_reason(status, probe=lambda _pid: "absent"))

    def test_unknown_phase_is_preserved(self):
        self.assertIsNone(
            orphaned_reason(
                self._status(current_phase="legacy-running"),
                probe=lambda _pid: "absent",
            )
        )

    def test_missing_malformed_or_nonpositive_pid_is_preserved(self):
        for pid in (None, "42", 0, -1, True):
            with self.subTest(pid=pid):
                self.assertIsNone(
                    orphaned_reason(self._status(pid=pid), probe=lambda _pid: "absent")
                )

    @mock.patch("dispatch_lib.reconcile.os.kill")
    def test_process_probe_distinguishes_absent_alive_and_ambiguous(self, kill):
        kill.return_value = None
        self.assertEqual(process_state(42), "alive")
        for error in (
            ProcessLookupError(),
            PermissionError(),
            OSError(),
            OverflowError(),
        ):
            with self.subTest(error=type(error).__name__):
                kill.side_effect = error
                self.assertEqual(
                    process_state(42),
                    "absent" if isinstance(error, ProcessLookupError) else "unknown",
                )


class ReconcileCommandTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.env = mock.patch.dict(os.environ, {"DISPATCH_ROOT": str(self.root)})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def _worker(self, worker_id="w-dead", pid=424242, phase="starting"):
        init_status(worker_id, "task", "fixture", pid)
        data = read_status(worker_id)
        data["current_phase"] = phase
        status_path(worker_id).write_text(json.dumps(data))

    @mock.patch.object(cli, "orphaned_reason")
    def test_dry_run_never_changes_status_or_registry(self, classify):
        classify.side_effect = lambda status: (
            "recorded process absent" if status.get("worker_id") == "w-dead" else None
        )
        self._worker()
        before = status_path("w-dead").read_bytes()

        cli.cmd_reconcile(SimpleNamespace(apply=False))

        self.assertEqual(status_path("w-dead").read_bytes(), before)
        self.assertFalse(registry_path().exists())
        self.assertFalse((self.root / "reconcile.lock").exists())

    @mock.patch.object(cli, "orphaned_reason")
    def test_apply_writes_terminal_receipt_event_and_releases_cwd_lock(self, classify):
        classify.side_effect = lambda status: (
            "recorded process absent" if status.get("worker_id") == "w-dead" else None
        )
        self._worker()
        lock_dir = self.root / "cwd-locks"
        lock_dir.mkdir(parents=True)
        # cwd_lock.release owns the exact filename; use its API to acquire it.
        from dispatch_lib import cwd_lock

        acquired, _ = cwd_lock.acquire("w-dead", str(self.root / "worktree"))
        self.assertTrue(acquired)

        cli.cmd_reconcile(SimpleNamespace(apply=True))

        status = read_status("w-dead")
        self.assertEqual(status["current_phase"], "errored")
        self.assertEqual(status["exit_code"], 70)
        self.assertIsNotNone(status["finalized_at"])
        self.assertIn("Orphan reconciled", status["error_summary"])
        rows = [json.loads(line) for line in registry_path().read_text().splitlines()]
        self.assertEqual(rows[0]["event"], "worker_reconciled")
        self.assertEqual(rows[0]["previous_phase"], "starting")
        self.assertEqual(rows[0]["current_phase"], "errored")
        self.assertTrue(cwd_lock.acquire("w-next", str(self.root / "worktree"))[0])

    @mock.patch.object(cli, "orphaned_reason")
    def test_apply_rechecks_status_before_mutating(self, classify):
        self._worker()
        classify.side_effect = ["recorded process absent", None]

        cli.cmd_reconcile(SimpleNamespace(apply=True))

        self.assertEqual(read_status("w-dead")["current_phase"], "starting")
        self.assertFalse(registry_path().exists())


if __name__ == "__main__":
    unittest.main()
