"""Deadline admission tests: common expired/malformed/naive rejection.

The independent review's admission reproducer showed the installed gate
admitted top-level expired, top-level malformed, AND nested malformed
deadlines (only nested expired was rejected). These tests pin the fix:
every dispatch entrypoint (task/breakout start, answer, checkpoint
continue) rejects bad deadlines before any side effect, while valid and
missing deadlines keep working and propagate.

Isolation: every test runs against a temporary DISPATCH_ROOT and
DISPATCH_CHECKPOINT_ROOT; launches are faked by stubbing
cli.subprocess.Popen, so no real worker process is ever spawned.
"""
import contextlib
import io
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import cli
from dispatch_lib import checkpoint


def _iso(hours: float) -> str:
    when = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(hours=hours)
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


VALID_DEADLINE = _iso(1)
EXPIRED_DEADLINE = _iso(-1)
NAIVE_DEADLINE = "2099-01-01T00:00:00"
MALFORMED_DEADLINE = "not-a-deadline"


class DeadlineEvaluatorTests(unittest.TestCase):
    def test_missing_deadline_admits(self):
        for missing in (None, ""):
            ok, reason = cli.evaluate_deadline(missing)
            self.assertTrue(ok)
            self.assertEqual(reason, "")

    def test_valid_future_deadline_admits(self):
        ok, reason = cli.evaluate_deadline(VALID_DEADLINE)
        self.assertTrue(ok, reason)
        self.assertEqual(reason, "")

    def test_expired_deadline_rejects(self):
        ok, reason = cli.evaluate_deadline(EXPIRED_DEADLINE)
        self.assertFalse(ok)
        self.assertIn("DEADLINE_EXCEEDED", reason)

    def test_malformed_deadline_rejects(self):
        ok, reason = cli.evaluate_deadline(MALFORMED_DEADLINE)
        self.assertFalse(ok)
        self.assertIn("DEADLINE_MALFORMED", reason)

    def test_naive_deadline_rejects_as_ambiguous(self):
        ok, reason = cli.evaluate_deadline(NAIVE_DEADLINE)
        self.assertFalse(ok)
        self.assertIn("DEADLINE_AMBIGUOUS_TZ", reason)

    def test_non_string_deadline_rejects(self):
        ok, reason = cli.evaluate_deadline(12345)
        self.assertFalse(ok)
        self.assertIn("DEADLINE_MALFORMED", reason)


class DeadlineAdmissionEntrypointTests(unittest.TestCase):
    """Entrypoint behavior under isolated roots and faked launch effects."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.brief = self.root / "brief.md"
        self.brief.write_text("Do the bounded fixture task.\n")
        env = {
            "DISPATCH_ROOT": str(self.root),
            "DISPATCH_CHECKPOINT_ROOT": str(self.root / "checkpoints"),
        }
        self.env = mock.patch.dict(os.environ, env)
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    # -- fixtures --

    @contextlib.contextmanager
    def _patched(self):
        """Stub matrix, routing, permission, worker id, and the launch effect.

        The launch effect (Popen) is faked; the mock is yielded so tests can
        assert on calls and the launch environment.
        """
        popen = mock.Mock(return_value=SimpleNamespace(pid=98765))
        patches = [
            mock.patch.object(cli, "_load_matrix", return_value={
                "executors": {"fixture": {"wrapper": "_exec.sh"}}
            }),
            mock.patch.object(cli, "auto_route", return_value=("fixture", "high")),
            # fixture is not in the real matrix's nesting pairs (and self-
            # dispatch is always denied); admission is what's under test.
            mock.patch.object(cli, "check_nested_permission",
                              return_value=(True, "fixture pair allowed")),
            mock.patch.object(cli, "_generate_worker_id",
                              side_effect=lambda slug: f"w-test-{abs(hash(slug)) % 10000}"),
            mock.patch.object(cli.subprocess, "Popen", popen),
        ]
        with contextlib.ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            yield popen

    @contextlib.contextmanager
    def _nested_env(self):
        os.environ["DISPATCH_NESTED"] = "1"
        try:
            yield
        finally:
            os.environ.pop("DISPATCH_NESTED", None)

    @contextlib.contextmanager
    def _stderr(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            yield err

    def _start_args(self, deadline=None, parent_id=None):
        # depth stays 0 for nested fixtures: the depth cap is 1 and these
        # tests exercise deadline admission, not the depth gate.
        return SimpleNamespace(
            executor="fixture", task_file=str(self.brief), task=None,
            cwd=str(self.root), slug="fixture", parent_id=parent_id,
            parent_executor="fixture" if parent_id else None, depth=0,
            budget_remaining=5.0 if parent_id else None, deadline=deadline,
        )

    def _launch_expect_rejected(self, args, label):
        with self._patched() as popen, self._stderr() as err:
            with self.assertRaises(SystemExit) as stopped:
                cli.cmd_start(args, "task")
        self.assertEqual(stopped.exception.code, 6)
        self.assertIn(label, err.getvalue())
        popen.assert_not_called()
        self.assertFalse((self.root / "status").exists(), "no status row on rejection")
        self.assertFalse((self.root / "session_registry.jsonl").exists(),
                         "no registry row on rejection")
        self.assertFalse((self.root / "locks").exists(), "no cwd lock on rejection")

    def _last_status(self):
        """Most recently written status row (answer/continue leave prior+new)."""
        files = sorted((self.root / "status").glob("*.json"),
                       key=lambda p: p.stat().st_mtime)
        self.assertTrue(files, "expected a status row")
        return json.loads(files[-1].read_text())

    @staticmethod
    def _intent_files(root):
        intents = root / "workflow" / "intents"
        return list(intents.glob("*.json")) if intents.exists() else []

    # -- start: the three reproduced bad admissions now reject --

    def test_start_top_level_expired_rejected(self):
        self._launch_expect_rejected(self._start_args(deadline=EXPIRED_DEADLINE),
                                     "DEADLINE_EXCEEDED")

    def test_start_top_level_malformed_rejected(self):
        self._launch_expect_rejected(self._start_args(deadline=MALFORMED_DEADLINE),
                                     "DEADLINE_MALFORMED")

    def test_start_top_level_naive_rejected(self):
        self._launch_expect_rejected(self._start_args(deadline=NAIVE_DEADLINE),
                                     "DEADLINE_AMBIGUOUS_TZ")

    def test_start_nested_malformed_rejected(self):
        with self._nested_env():
            self._launch_expect_rejected(
                self._start_args(deadline=MALFORMED_DEADLINE, parent_id="w-parent"),
                "DEADLINE_MALFORMED")

    def test_start_nested_expired_still_rejected(self):
        with self._nested_env():
            self._launch_expect_rejected(
                self._start_args(deadline=EXPIRED_DEADLINE, parent_id="w-parent"),
                "DEADLINE_EXCEEDED")

    # -- start: valid and missing deadlines keep working --

    def test_start_top_level_valid_launches_with_deadline_env(self):
        with self._patched() as popen:
            cli.cmd_start(self._start_args(deadline=VALID_DEADLINE), "task")
        popen.assert_called_once()
        env = popen.call_args.kwargs["env"]
        self.assertEqual(env.get("DISPATCH_DEADLINE"), VALID_DEADLINE)
        self.assertNotIn("DISPATCH_NESTED", env)
        self.assertEqual(self._last_status().get("deadline"), VALID_DEADLINE)

    def test_start_top_level_no_deadline_launches_without_deadline_env(self):
        with self._patched() as popen:
            cli.cmd_start(self._start_args(deadline=None), "task")
        popen.assert_called_once()
        self.assertNotIn("DISPATCH_DEADLINE", popen.call_args.kwargs["env"])
        self.assertIsNone(self._last_status().get("deadline"))

    def test_start_nested_valid_launches_with_deadline_env(self):
        with self._nested_env(), self._patched() as popen:
            cli.cmd_start(
                self._start_args(deadline=VALID_DEADLINE, parent_id="w-parent"),
                "task")
        popen.assert_called_once()
        env = popen.call_args.kwargs["env"]
        self.assertEqual(env.get("DISPATCH_DEADLINE"), VALID_DEADLINE)
        self.assertEqual(env.get("DISPATCH_NESTED"), "1")

    # -- answer: inherited deadline admitted before side effects --

    def _make_prior_status(self, worker_id, deadline, with_question=False):
        cli.init_status(
            worker_id=worker_id, mode="task", executor="fixture", pid=111,
            brief_path=str(self.brief), deadline=deadline,
        )
        if with_question:
            qfile = self.root / "questions" / f"{worker_id}.md"
            qfile.parent.mkdir(parents=True, exist_ok=True)
            qfile.write_text("question body")

    def _answer_rejected(self, worker_id, label):
        with self._patched() as popen, self._stderr() as err:
            with self.assertRaises(SystemExit) as stopped:
                cli.cmd_answer(SimpleNamespace(worker_id=worker_id,
                                               answer="the answer", answer_file=None))
        self.assertEqual(stopped.exception.code, 6)
        self.assertIn(label, err.getvalue())
        popen.assert_not_called()
        self.assertFalse((self.root / "tasks").exists(), "no task archive write")
        self.assertFalse((self.root / "questions" / "_resolved").exists(),
                         "question file not resolved")
        self.assertFalse((self.root / "session_registry.jsonl").exists(),
                         "no registry rows")

    def test_answer_expired_inherited_deadline_rejected(self):
        self._make_prior_status("w-prior-answer", EXPIRED_DEADLINE, with_question=True)
        self._answer_rejected("w-prior-answer", "DEADLINE_EXCEEDED")

    def test_answer_malformed_inherited_deadline_rejected(self):
        self._make_prior_status("w-prior-answer", MALFORMED_DEADLINE, with_question=True)
        self._answer_rejected("w-prior-answer", "DEADLINE_MALFORMED")

    def test_answer_inherits_valid_deadline(self):
        self._make_prior_status("w-prior-answer", VALID_DEADLINE)
        with self._patched() as popen:
            cli.cmd_answer(SimpleNamespace(worker_id="w-prior-answer",
                                           answer="the answer", answer_file=None))
        popen.assert_called_once()
        env = popen.call_args.kwargs["env"]
        self.assertEqual(env.get("DISPATCH_DEADLINE"), VALID_DEADLINE)
        self.assertEqual(self._last_status().get("deadline"), VALID_DEADLINE)

    def test_answer_without_deadline_launches_without_reset(self):
        self._make_prior_status("w-prior-answer", None)
        with self._patched() as popen:
            cli.cmd_answer(SimpleNamespace(worker_id="w-prior-answer",
                                           answer="the answer", answer_file=None))
        popen.assert_called_once()
        self.assertNotIn("DISPATCH_DEADLINE", popen.call_args.kwargs["env"])
        self.assertIsNone(self._last_status().get("deadline"))

    # -- checkpoint continue: inherited deadline before consumption/intent --

    def _make_checkpoint(self, worker_id, deadline):
        checkpoint.write_checkpoint_file(
            slug="fixture", phase="1", worker_id=worker_id,
            commit_sha="source-revision", directive="pause-for-review",
        )
        self._make_prior_status(worker_id, deadline)

    def _continue_rejected(self, worker_id, label):
        args = SimpleNamespace(worker_id=worker_id, worktree=None,
                               task_file=str(self.brief), executor="fixture")
        with self._patched() as popen, self._stderr() as err:
            with self.assertRaises(SystemExit) as stopped:
                cli.cmd_checkpoint_continue(args)
        self.assertEqual(stopped.exception.code, 6)
        self.assertIn(label, err.getvalue())
        popen.assert_not_called()
        self.assertIsNotNone(checkpoint.find_checkpoint_by_worker(worker_id),
                             "checkpoint not consumed on rejection")
        self.assertEqual(self._intent_files(self.root), [],
                         "no launch intent mutation on rejection")

    def test_checkpoint_continue_expired_inherited_deadline_rejected(self):
        self._make_checkpoint("w-prior-ck", EXPIRED_DEADLINE)
        self._continue_rejected("w-prior-ck", "DEADLINE_EXCEEDED")

    def test_checkpoint_continue_malformed_inherited_deadline_rejected(self):
        self._make_checkpoint("w-prior-ck", MALFORMED_DEADLINE)
        self._continue_rejected("w-prior-ck", "DEADLINE_MALFORMED")

    def test_checkpoint_continue_inherits_valid_deadline(self):
        self._make_checkpoint("w-prior-ck", VALID_DEADLINE)
        args = SimpleNamespace(worker_id="w-prior-ck", worktree=None,
                               task_file=str(self.brief), executor="fixture")
        with self._patched() as popen:
            cli.cmd_checkpoint_continue(args)
        popen.assert_called_once()
        env = popen.call_args.kwargs["env"]
        self.assertEqual(env.get("DISPATCH_DEADLINE"), VALID_DEADLINE)
        self.assertEqual(self._last_status().get("deadline"), VALID_DEADLINE)
        self.assertIsNone(checkpoint.find_checkpoint_by_worker("w-prior-ck"),
                          "checkpoint consumed after clean admission")
        intents = self._intent_files(self.root)
        self.assertEqual(len(intents), 1)
        self.assertEqual(json.loads(intents[0].read_text())["state"], "launch_started")

    def test_checkpoint_continue_without_deadline_launches_without_reset(self):
        self._make_checkpoint("w-prior-ck", None)
        args = SimpleNamespace(worker_id="w-prior-ck", worktree=None,
                               task_file=str(self.brief), executor="fixture")
        with self._patched() as popen:
            cli.cmd_checkpoint_continue(args)
        popen.assert_called_once()
        self.assertNotIn("DISPATCH_DEADLINE", popen.call_args.kwargs["env"])
        self.assertIsNone(self._last_status().get("deadline"))


if __name__ == "__main__":
    unittest.main()
