import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import cli
from dispatch_lib.path_conventions import (
    reconcile_pending_dir,
    registry_path,
    status_path,
)
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

    @staticmethod
    def _absent(status):
        return (
            "recorded process is absent"
            if status.get("worker_id") == "w-dead"
            else None
        )

    def _events(self):
        if not registry_path().exists():
            return []
        return [json.loads(line) for line in registry_path().read_text().splitlines()]

    @mock.patch.object(cli, "orphaned_reason")
    def test_dry_run_never_changes_status_or_registry(self, classify):
        classify.side_effect = self._absent
        self._worker()
        before = status_path("w-dead").read_bytes()

        cli.cmd_reconcile(SimpleNamespace(apply=False))

        self.assertEqual(status_path("w-dead").read_bytes(), before)
        self.assertFalse(registry_path().exists())
        self.assertFalse((self.root / "reconcile.lock").exists())

    @mock.patch.object(cli, "orphaned_reason")
    def test_apply_writes_terminal_receipt_event_and_releases_cwd_lock(self, classify):
        classify.side_effect = self._absent
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
        rows = self._events()
        self.assertEqual(rows[0]["event"], "worker_reconciled")
        self.assertEqual(len(rows[0]["transaction_id"]), 32)
        self.assertEqual(rows[0]["previous_phase"], "starting")
        self.assertEqual(rows[0]["current_phase"], "errored")
        self.assertTrue(cwd_lock.acquire("w-next", str(self.root / "worktree"))[0])

    @mock.patch.object(cli, "orphaned_reason")
    def test_apply_rechecks_status_before_mutating(self, classify):
        self._worker()
        classify.side_effect = ["recorded process is absent", None]

        cli.cmd_reconcile(SimpleNamespace(apply=True))

        self.assertEqual(read_status("w-dead")["current_phase"], "starting")
        self.assertFalse(registry_path().exists())

    @mock.patch.object(cli, "orphaned_reason")
    def test_append_failure_is_recovered_once_from_durable_intent(self, classify):
        classify.side_effect = self._absent
        self._worker()
        from dispatch_lib import cwd_lock

        worktree = str(self.root / "worktree")
        self.assertTrue(cwd_lock.acquire("w-dead", worktree)[0])
        stderr = StringIO()
        with (
            mock.patch.object(
                cli, "_append_registry_once", side_effect=OSError("/private/crash")
            ),
            redirect_stderr(stderr),
        ):
            with self.assertRaisesRegex(SystemExit, "75"):
                cli.cmd_reconcile(SimpleNamespace(apply=True))

        self.assertEqual(read_status("w-dead")["current_phase"], "errored")
        self.assertFalse(cwd_lock.held_by("w-dead"))
        self.assertTrue((reconcile_pending_dir() / "w-dead.json").is_file())
        self.assertEqual(self._events(), [])
        self.assertNotIn("/private", stderr.getvalue())
        self.assertEqual(
            stderr.getvalue().strip(),
            "Reconciliation refused: durable state update failed",
        )

        cli.cmd_reconcile(SimpleNamespace(apply=True))
        self.assertEqual(len(self._events()), 1)
        self.assertFalse((reconcile_pending_dir() / "w-dead.json").exists())

    @mock.patch.object(cli, "orphaned_reason")
    def test_torn_event_append_is_truncated_and_recovered(self, classify):
        classify.side_effect = self._absent
        self._worker()
        real_write = os.write

        def torn_write(descriptor, payload):
            real_write(descriptor, payload[: max(1, len(payload) // 2)])
            raise OSError("crash during append")

        with mock.patch.object(cli.os, "write", side_effect=torn_write):
            with self.assertRaisesRegex(SystemExit, "75"):
                cli.cmd_reconcile(SimpleNamespace(apply=True))
        self.assertTrue((reconcile_pending_dir() / "w-dead.json").is_file())
        self.assertFalse(registry_path().read_bytes().endswith(b"\n"))

        cli.cmd_reconcile(SimpleNamespace(apply=True))
        self.assertEqual(len(self._events()), 1)
        self.assertFalse((reconcile_pending_dir() / "w-dead.json").exists())

    @mock.patch.object(cli, "orphaned_reason")
    def test_crash_before_finalize_recovers_status_lock_and_event(self, classify):
        classify.side_effect = self._absent
        self._worker()
        from dispatch_lib import cwd_lock

        self.assertTrue(cwd_lock.acquire("w-dead", str(self.root / "worktree"))[0])
        with mock.patch.object(cli, "finalize", side_effect=OSError("crash")):
            with self.assertRaisesRegex(SystemExit, "75"):
                cli.cmd_reconcile(SimpleNamespace(apply=True))
        self.assertEqual(read_status("w-dead")["current_phase"], "starting")
        self.assertTrue((reconcile_pending_dir() / "w-dead.json").is_file())

        cli.cmd_reconcile(SimpleNamespace(apply=True))
        self.assertEqual(read_status("w-dead")["current_phase"], "errored")
        self.assertFalse(cwd_lock.held_by("w-dead"))
        self.assertEqual(len(self._events()), 1)

    @mock.patch.object(cli, "orphaned_reason")
    def test_crash_after_event_append_deduplicates_on_recovery(self, classify):
        classify.side_effect = self._absent
        self._worker()
        with mock.patch.object(cli, "remove_intent", side_effect=OSError("crash")):
            with self.assertRaisesRegex(SystemExit, "75"):
                cli.cmd_reconcile(SimpleNamespace(apply=True))
        self.assertEqual(len(self._events()), 1)
        self.assertTrue((reconcile_pending_dir() / "w-dead.json").is_file())

        cli.cmd_reconcile(SimpleNamespace(apply=True))
        self.assertEqual(len(self._events()), 1)
        self.assertFalse((reconcile_pending_dir() / "w-dead.json").exists())

    @mock.patch.object(cli, "orphaned_reason")
    def test_cwd_release_failure_leaves_recoverable_intent(self, classify):
        classify.side_effect = self._absent
        self._worker()
        from dispatch_lib import cwd_lock

        self.assertTrue(cwd_lock.acquire("w-dead", str(self.root / "worktree"))[0])
        with mock.patch.object(
            cwd_lock, "release", side_effect=OSError("release failed")
        ):
            with self.assertRaisesRegex(SystemExit, "75"):
                cli.cmd_reconcile(SimpleNamespace(apply=True))
        self.assertTrue((reconcile_pending_dir() / "w-dead.json").is_file())
        self.assertEqual(self._events(), [])

        cli.cmd_reconcile(SimpleNamespace(apply=True))
        self.assertFalse(cwd_lock.held_by("w-dead"))
        self.assertEqual(len(self._events()), 1)

    @mock.patch.object(cli, "orphaned_reason")
    def test_status_file_fsync_failure_keeps_intent_for_exact_retry(self, classify):
        classify.side_effect = self._absent
        self._worker()
        from dispatch_lib import status_writer

        real_fsync = os.fsync
        calls = 0

        def fail_status_file_fsync(descriptor):
            nonlocal calls
            calls += 1
            if calls == 3:
                raise OSError("status file fsync")
            return real_fsync(descriptor)

        with mock.patch.object(
            status_writer.os, "fsync", side_effect=fail_status_file_fsync
        ):
            with self.assertRaisesRegex(SystemExit, "75"):
                cli.cmd_reconcile(SimpleNamespace(apply=True))

        self.assertEqual(read_status("w-dead")["current_phase"], "starting")
        self.assertTrue((reconcile_pending_dir() / "w-dead.json").is_file())
        self.assertEqual(self._events(), [])

        cli.cmd_reconcile(SimpleNamespace(apply=True))
        self.assertEqual(read_status("w-dead")["current_phase"], "errored")
        self.assertEqual(len(self._events()), 1)
        self.assertFalse((reconcile_pending_dir() / "w-dead.json").exists())

    @mock.patch.object(cli, "orphaned_reason")
    def test_status_directory_fsync_failure_keeps_intent_for_exact_retry(
        self, classify
    ):
        classify.side_effect = self._absent
        self._worker()
        from dispatch_lib import status_writer

        with mock.patch.object(
            status_writer, "_fsync_directory", side_effect=OSError("status dir fsync")
        ):
            with self.assertRaisesRegex(SystemExit, "75"):
                cli.cmd_reconcile(SimpleNamespace(apply=True))

        self.assertEqual(read_status("w-dead")["current_phase"], "errored")
        self.assertTrue((reconcile_pending_dir() / "w-dead.json").is_file())
        self.assertEqual(self._events(), [])

        with mock.patch.object(
            cli, "confirm_status_durable", wraps=cli.confirm_status_durable
        ) as confirm:
            cli.cmd_reconcile(SimpleNamespace(apply=True))
        confirm.assert_called_once()
        self.assertEqual(len(self._events()), 1)
        self.assertFalse((reconcile_pending_dir() / "w-dead.json").exists())

    @mock.patch.object(cli, "orphaned_reason")
    def test_cwd_directory_fsync_failure_retries_absence_before_event(self, classify):
        classify.side_effect = self._absent
        self._worker()
        from dispatch_lib import cwd_lock

        worktree = str(self.root / "worktree")
        self.assertTrue(cwd_lock.acquire("w-dead", worktree)[0])
        with mock.patch.object(
            cwd_lock, "_fsync_directory", side_effect=OSError("cwd dir fsync")
        ):
            with self.assertRaisesRegex(SystemExit, "75"):
                cli.cmd_reconcile(SimpleNamespace(apply=True))

        self.assertFalse(cwd_lock.held_by("w-dead"))
        self.assertTrue((reconcile_pending_dir() / "w-dead.json").is_file())
        self.assertEqual(self._events(), [])
        self.assertTrue(cwd_lock.acquire("w-next", worktree)[0])

        cli.cmd_reconcile(SimpleNamespace(apply=True))
        self.assertFalse(cwd_lock.held_by("w-dead"))
        self.assertTrue(cwd_lock.held_by("w-next"))
        self.assertEqual(len(self._events()), 1)
        self.assertFalse((reconcile_pending_dir() / "w-dead.json").exists())

    @mock.patch.object(cli, "orphaned_reason")
    def test_new_registry_parent_fsync_failure_recovers_without_duplicate(
        self, classify
    ):
        classify.side_effect = self._absent
        self._worker()
        with mock.patch.object(
            cli, "_fsync_directory", side_effect=OSError("registry parent fsync")
        ):
            with self.assertRaisesRegex(SystemExit, "75"):
                cli.cmd_reconcile(SimpleNamespace(apply=True))

        self.assertEqual(len(self._events()), 1)
        self.assertTrue((reconcile_pending_dir() / "w-dead.json").is_file())

        cli.cmd_reconcile(SimpleNamespace(apply=True))
        self.assertEqual(len(self._events()), 1)
        self.assertFalse((reconcile_pending_dir() / "w-dead.json").exists())

    @mock.patch.object(cli, "orphaned_reason")
    def test_new_registry_file_fsync_failure_recovers_without_duplicate(self, classify):
        classify.side_effect = self._absent
        self._worker()
        real_fsync = os.fsync
        failed = False

        def fail_new_registry_fsync(descriptor):
            nonlocal failed
            path = registry_path()
            if not failed and path.exists():
                descriptor_info = os.fstat(descriptor)
                registry_info = path.stat()
                if (
                    descriptor_info.st_dev == registry_info.st_dev
                    and descriptor_info.st_ino == registry_info.st_ino
                ):
                    failed = True
                    raise OSError("registry file fsync")
            return real_fsync(descriptor)

        with mock.patch.object(cli.os, "fsync", side_effect=fail_new_registry_fsync):
            with self.assertRaisesRegex(SystemExit, "75"):
                cli.cmd_reconcile(SimpleNamespace(apply=True))

        self.assertTrue(failed)
        self.assertEqual(len(self._events()), 1)
        self.assertTrue((reconcile_pending_dir() / "w-dead.json").is_file())

        cli.cmd_reconcile(SimpleNamespace(apply=True))
        self.assertEqual(len(self._events()), 1)
        self.assertFalse((reconcile_pending_dir() / "w-dead.json").exists())

    @mock.patch.object(cli, "orphaned_reason")
    def test_matching_registry_event_must_fsync_before_dedupe(self, classify):
        classify.side_effect = self._absent
        self._worker()
        with mock.patch.object(cli, "remove_intent", side_effect=OSError("crash")):
            with self.assertRaisesRegex(SystemExit, "75"):
                cli.cmd_reconcile(SimpleNamespace(apply=True))
        self.assertEqual(len(self._events()), 1)
        self.assertTrue((reconcile_pending_dir() / "w-dead.json").is_file())

        real_fsync = os.fsync
        calls = 0

        def fail_registry_fsync(descriptor):
            nonlocal calls
            calls += 1
            # status file + status directory + cwd-lock directory are synced
            # before the matching registry row becomes the fourth edge.
            if calls == 4:
                raise OSError("matching event fsync")
            return real_fsync(descriptor)

        with mock.patch.object(cli.os, "fsync", side_effect=fail_registry_fsync):
            with self.assertRaisesRegex(SystemExit, "75"):
                cli.cmd_reconcile(SimpleNamespace(apply=True))

        self.assertEqual(len(self._events()), 1)
        self.assertTrue((reconcile_pending_dir() / "w-dead.json").is_file())

        cli.cmd_reconcile(SimpleNamespace(apply=True))
        self.assertEqual(len(self._events()), 1)
        self.assertFalse((reconcile_pending_dir() / "w-dead.json").exists())

    def test_filename_content_mismatch_and_symlink_are_never_candidates(self):
        status = self.root / "status"
        status.mkdir()
        (status / "w-safe.json").write_text(
            json.dumps(
                {
                    "worker_id": "../../escape",
                    "current_phase": "starting",
                    "pid": 424242,
                    "finalized_at": None,
                }
            )
        )
        (status / "w-linked.json").symlink_to(status / "w-safe.json")

        cli.cmd_reconcile(SimpleNamespace(apply=False))

        self.assertFalse(registry_path().exists())
        self.assertFalse((self.root / "reconcile.lock").exists())

    def test_incomplete_bounded_snapshot_refuses_without_writes(self):
        self._worker()
        incomplete = {
            "source_generation": {"consistent": True},
            "coverage": {"complete": False, "stop_reason": "ENTRY_LIMIT"},
        }
        with mock.patch("dispatch_lib.reconcile.build_index", return_value=incomplete):
            with self.assertRaisesRegex(SystemExit, "75"):
                cli.cmd_reconcile(SimpleNamespace(apply=False))
        self.assertFalse(registry_path().exists())
        self.assertFalse((self.root / "reconcile.lock").exists())


if __name__ == "__main__":
    unittest.main()
