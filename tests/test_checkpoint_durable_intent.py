import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import cli
from dispatch_lib import checkpoint


class CheckpointDurableIntentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.worktree = self.root / "worktree"
        self.worktree.mkdir()
        self.brief = self.root / "brief.md"
        self.brief.write_text("Continue the approved bounded task.\n")
        self.env = mock.patch.dict(os.environ, {
            "DISPATCH_ROOT": str(self.root),
            "DISPATCH_CHECKPOINT_ROOT": str(self.root / "checkpoints"),
        })
        self.env.start()
        checkpoint.write_checkpoint_file(
            slug="fixture", phase="1", worker_id="w-prior-fixture",
            commit_sha="source-revision", next_phase="2",
            directive="pause-for-review",
        )
        # A real paused worker always has a stored status row (write_and_exit
        # finalizes it). Deadline admission now rejects a checkpoint whose
        # lineage status is missing, so the fixture records the prior row's
        # explicit disposition (unbounded) like a live pause would.
        cli.init_status(
            worker_id="w-prior-fixture", mode="breakout", executor="fixture",
            pid=424242, brief_path=str(self.brief), deadline=None,
        )
        self.args = SimpleNamespace(
            worker_id="w-prior-fixture", worktree=str(self.worktree),
            task_file=str(self.brief), executor="fixture",
        )

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def _patches(self):
        return (
            mock.patch.object(cli, "_load_matrix", return_value={
                "executors": {"fixture": {"wrapper": "_exec.sh"}}
            }),
            mock.patch.object(cli, "_generate_worker_id", return_value="w-resume-fixture"),
        )

    def _intent_record(self):
        paths = list((self.root / "workflow" / "intents").glob("*.json"))
        self.assertEqual(len(paths), 1)
        return json.loads(paths[0].read_text())

    def test_spawn_failure_keeps_checkpoint_pending_and_allows_exact_retry(self):
        matrix_patch, id_patch = self._patches()
        with matrix_patch, id_patch, mock.patch.object(
            cli.subprocess, "Popen", side_effect=OSError("spawn failed")
        ):
            with self.assertRaises(OSError):
                cli.cmd_checkpoint_continue(self.args)

        self.assertIsNotNone(checkpoint.find_checkpoint_by_worker("w-prior-fixture"))
        self.assertEqual(self._intent_record()["state"], "launch_not_started")

        matrix_patch, id_patch = self._patches()
        with matrix_patch, id_patch, mock.patch.object(
            cli.subprocess, "Popen", return_value=SimpleNamespace(pid=12345)
        ):
            cli.cmd_checkpoint_continue(self.args)

        self.assertIsNone(checkpoint.find_checkpoint_by_worker("w-prior-fixture"))
        self.assertEqual(self._intent_record()["state"], "launch_started")

    def test_post_spawn_crash_keeps_checkpoint_and_blocks_blind_retry(self):
        matrix_patch, id_patch = self._patches()
        popen = mock.Mock(return_value=SimpleNamespace(pid=12345))
        with matrix_patch, id_patch, mock.patch.object(cli.subprocess, "Popen", popen), \
                mock.patch.object(cli, "init_status", side_effect=RuntimeError("crash")):
            with self.assertRaises(RuntimeError):
                cli.cmd_checkpoint_continue(self.args)

        self.assertIsNotNone(checkpoint.find_checkpoint_by_worker("w-prior-fixture"))
        self.assertEqual(self._intent_record()["state"], "launch_started")

        matrix_patch, id_patch = self._patches()
        with matrix_patch, id_patch, mock.patch.object(cli.subprocess, "Popen", popen):
            with self.assertRaises(SystemExit) as stopped:
                cli.cmd_checkpoint_continue(self.args)
        self.assertEqual(stopped.exception.code, 4)
        self.assertEqual(popen.call_count, 1)


if __name__ == "__main__":
    unittest.main()
