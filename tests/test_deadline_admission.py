"""Deadline admission tests: common expired/malformed/naive rejection.

The independent review's admission reproducer showed the installed gate
admitted top-level expired, top-level malformed, AND nested malformed
deadlines (only nested expired was rejected). These tests pin the fix:
every dispatch entrypoint (task/breakout start, answer, checkpoint
continue) rejects bad deadlines before any side effect, while valid and
missing deadlines keep working and propagate.

The CS QA of candidate 23f304c (DEADLINE-23F304C-SCIENTIFIC-QA) added the
inheritance regression: an expired bound inherited through the launch
environment bypassed the first gate entirely, and a later --deadline could
extend it. These tests pin the resolution order — the effective deadline is
the earliest of the applicable inherited and explicit bounds, resolved
before the first effect (ensure_dirs), with corrupt inherited metadata
failing closed instead of manufacturing an unbounded resume.

The CS QA of bad52daf (DEADLINE-BAD52DA-SCIENTIFIC-QA) added the lost-
lineage regression: a checkpoint continuation whose stored status row is
missing resumed unbounded, consumed the checkpoint, and wrote a null
deadline. These tests pin the explicit lineage dispositions — missing,
corrupt, and legacy rows without a deadline key reject before any effect
(DEADLINE_LINEAGE_UNKNOWN, exit 6); a stored explicit null stays genuinely
unbounded.

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
from dispatch_lib.path_conventions import status_path


def _iso(hours: float) -> str:
    when = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(hours=hours)
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


VALID_DEADLINE = _iso(1)
EXPIRED_DEADLINE = _iso(-1)
NAIVE_DEADLINE = "2099-01-01T00:00:00"
MALFORMED_DEADLINE = "not-a-deadline"
FAR_FUTURE_DEADLINE = "2099-01-01T00:00:00Z"


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


class ResolveEffectiveDeadlineTests(unittest.TestCase):
    """Unit contract of the inherited+explicit resolution."""

    def test_no_bounds_is_genuinely_unbounded(self):
        ok, reason, effective = cli.resolve_effective_deadline(None, None)
        self.assertTrue(ok)
        self.assertEqual(reason, "")
        self.assertIsNone(effective)

    def test_explicit_alone_is_effective(self):
        ok, _, effective = cli.resolve_effective_deadline(VALID_DEADLINE, None)
        self.assertTrue(ok)
        self.assertEqual(effective, VALID_DEADLINE)

    def test_inherited_alone_is_effective(self):
        ok, _, effective = cli.resolve_effective_deadline(None, VALID_DEADLINE)
        self.assertTrue(ok)
        self.assertEqual(effective, VALID_DEADLINE)

    def test_earliest_bound_wins_both_ways(self):
        ok, _, effective = cli.resolve_effective_deadline(
            VALID_DEADLINE, FAR_FUTURE_DEADLINE)
        self.assertTrue(ok)
        self.assertEqual(effective, VALID_DEADLINE)
        ok, _, effective = cli.resolve_effective_deadline(
            FAR_FUTURE_DEADLINE, VALID_DEADLINE)
        self.assertTrue(ok)
        self.assertEqual(effective, VALID_DEADLINE)

    def test_inherited_expired_rejects_despite_later_explicit(self):
        ok, reason, effective = cli.resolve_effective_deadline(
            FAR_FUTURE_DEADLINE, EXPIRED_DEADLINE)
        self.assertFalse(ok)
        self.assertIn("DEADLINE_EXCEEDED", reason)
        self.assertIn("inherited DISPATCH_DEADLINE", reason)
        self.assertIsNone(effective)

    def test_inherited_malformed_rejects(self):
        ok, reason, _ = cli.resolve_effective_deadline(VALID_DEADLINE, MALFORMED_DEADLINE)
        self.assertFalse(ok)
        self.assertIn("DEADLINE_MALFORMED", reason)

    def test_inherited_naive_rejects(self):
        ok, reason, _ = cli.resolve_effective_deadline(VALID_DEADLINE, NAIVE_DEADLINE)
        self.assertFalse(ok)
        self.assertIn("DEADLINE_AMBIGUOUS_TZ", reason)

    def test_inherited_empty_rejects_as_corrupt(self):
        ok, reason, _ = cli.resolve_effective_deadline(None, "")
        self.assertFalse(ok)
        self.assertIn("DEADLINE_MALFORMED", reason)

    def test_inherited_non_string_rejects(self):
        ok, reason, _ = cli.resolve_effective_deadline(None, 12345)
        self.assertFalse(ok)
        self.assertIn("DEADLINE_MALFORMED", reason)

    def test_explicit_malformed_rejects(self):
        ok, reason, _ = cli.resolve_effective_deadline(MALFORMED_DEADLINE, VALID_DEADLINE)
        self.assertFalse(ok)
        self.assertIn("DEADLINE_MALFORMED", reason)

    def test_custom_source_label_named_in_rejection(self):
        ok, reason, _ = cli.resolve_effective_deadline(
            None, EXPIRED_DEADLINE, source="stored worker deadline")
        self.assertFalse(ok)
        self.assertIn("stored worker deadline", reason)


class _IsolatedDispatchRoot(unittest.TestCase):
    """Shared fixtures: temporary roots, stubbed routing, faked launches."""

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
    def _env_deadline(self, value):
        """Set an inherited DISPATCH_DEADLINE in the controller environment."""
        with mock.patch.dict(os.environ, {cli.DEADLINE_ENV_VAR: value}):
            yield

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


class DeadlineAdmissionEntrypointTests(_IsolatedDispatchRoot):
    """Entrypoint behavior under isolated roots and faked launch effects."""

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

    def test_checkpoint_continue_expired_inherited_deadline_rejected(self):
        self._make_checkpoint("w-prior-ck", EXPIRED_DEADLINE)
        self._continue_rejected("w-prior-ck", "DEADLINE_EXCEEDED")

    def test_checkpoint_continue_malformed_inherited_deadline_rejected(self):
        self._make_checkpoint("w-prior-ck", MALFORMED_DEADLINE)
        self._continue_rejected("w-prior-ck", "DEADLINE_MALFORMED")

    def test_checkpoint_continue_naive_inherited_deadline_rejected(self):
        self._make_checkpoint("w-prior-ck", NAIVE_DEADLINE)
        self._continue_rejected("w-prior-ck", "DEADLINE_AMBIGUOUS_TZ")

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


class InheritedDeadlineBoundaryTests(_IsolatedDispatchRoot):
    """E07 regression: the launch-lineage bound must gate start before effects.

    CS QA of 23f304c reproduced, via cli.cmd_start with DISPATCH_DEADLINE in
    the environment, that an inherited expired bound bypassed the first gate
    (reaching ensure_dirs) both alone and under a later explicit --deadline.
    """

    def _start_expect_rejected_before_first_effect(self, deadline, label):
        args = self._start_args(deadline=deadline)
        with mock.patch.object(cli, "ensure_dirs") as ensure:
            with self._patched() as popen, self._stderr() as err:
                with self.assertRaises(SystemExit) as stopped:
                    cli.cmd_start(args, "task")
        self.assertEqual(stopped.exception.code, 6)
        self.assertIn(label, err.getvalue())
        ensure.assert_not_called()
        popen.assert_not_called()
        self.assertFalse((self.root / "status").exists(), "no status row on rejection")
        self.assertFalse((self.root / "session_registry.jsonl").exists(),
                         "no registry row on rejection")
        self.assertFalse((self.root / "locks").exists(), "no cwd lock on rejection")

    # -- the two reproduced counterexamples --

    def test_start_inherited_expired_rejected_before_first_effect(self):
        with self._env_deadline(EXPIRED_DEADLINE):
            self._start_expect_rejected_before_first_effect(
                None, "DEADLINE_EXCEEDED")

    def test_start_inherited_expired_not_extended_by_later_explicit(self):
        # Mirrors the QA counterexample: nested child with parent linkage,
        # inherited expired bound, later explicit --deadline must not extend.
        with self._nested_env(), self._env_deadline(EXPIRED_DEADLINE):
            args = self._start_args(deadline=FAR_FUTURE_DEADLINE,
                                    parent_id="owned-parent")
            with mock.patch.object(cli, "ensure_dirs") as ensure:
                with self._patched() as popen, self._stderr() as err:
                    with self.assertRaises(SystemExit) as stopped:
                        cli.cmd_start(args, "task")
        self.assertEqual(stopped.exception.code, 6)
        self.assertIn("DEADLINE_EXCEEDED", err.getvalue())
        self.assertIn("inherited DISPATCH_DEADLINE", err.getvalue())
        ensure.assert_not_called()
        popen.assert_not_called()
        self.assertFalse((self.root / "session_registry.jsonl").exists(),
                         "no registry row on rejection")

    # -- all inherited rejection shapes at start --

    def test_start_inherited_malformed_rejected(self):
        with self._env_deadline(MALFORMED_DEADLINE):
            self._start_expect_rejected_before_first_effect(
                None, "DEADLINE_MALFORMED")

    def test_start_inherited_naive_rejected(self):
        with self._env_deadline(NAIVE_DEADLINE):
            self._start_expect_rejected_before_first_effect(
                None, "DEADLINE_AMBIGUOUS_TZ")

    def test_start_inherited_empty_env_rejected_as_corrupt(self):
        # Present-but-empty is degenerate metadata, not a missing deadline.
        with self._env_deadline(""):
            self._start_expect_rejected_before_first_effect(
                None, "DEADLINE_MALFORMED")

    def test_start_inherited_malformed_rejected_despite_valid_explicit(self):
        with self._env_deadline(MALFORMED_DEADLINE):
            self._start_expect_rejected_before_first_effect(
                VALID_DEADLINE, "DEADLINE_MALFORMED")

    # -- valid inheritance keeps working, earliest bound wins --

    def test_start_inherited_valid_without_explicit_propagates(self):
        with self._patched() as popen, self._env_deadline(VALID_DEADLINE):
            cli.cmd_start(self._start_args(deadline=None), "task")
        popen.assert_called_once()
        env = popen.call_args.kwargs["env"]
        self.assertEqual(env.get("DISPATCH_DEADLINE"), VALID_DEADLINE)
        self.assertEqual(self._last_status().get("deadline"), VALID_DEADLINE)

    def test_start_explicit_earlier_tightens_inherited_later_bound(self):
        # earlier-child case: child's own tighter bound is carried forward.
        with self._patched() as popen, self._env_deadline(FAR_FUTURE_DEADLINE):
            cli.cmd_start(self._start_args(deadline=VALID_DEADLINE), "task")
        popen.assert_called_once()
        env = popen.call_args.kwargs["env"]
        self.assertEqual(env.get("DISPATCH_DEADLINE"), VALID_DEADLINE)
        self.assertEqual(self._last_status().get("deadline"), VALID_DEADLINE)

    def test_start_inherited_earlier_bound_survives_later_explicit(self):
        # future-parent case: a later child --deadline cannot extend the bound.
        with self._patched() as popen, self._env_deadline(VALID_DEADLINE):
            cli.cmd_start(self._start_args(deadline=FAR_FUTURE_DEADLINE), "task")
        popen.assert_called_once()
        env = popen.call_args.kwargs["env"]
        self.assertEqual(env.get("DISPATCH_DEADLINE"), VALID_DEADLINE)
        self.assertEqual(self._last_status().get("deadline"), VALID_DEADLINE)

    # -- deliberate resume boundary: answer/continue inherit stored status --

    def test_answer_stale_controller_env_does_not_bind_child(self):
        # The answering controller's own env is not the resume lineage; the
        # relaunched child must not silently inherit an unrelated deadline.
        self._make_prior_status("w-prior-answer", None)
        with self._patched() as popen, self._env_deadline(VALID_DEADLINE):
            cli.cmd_answer(SimpleNamespace(worker_id="w-prior-answer",
                                           answer="the answer", answer_file=None))
        popen.assert_called_once()
        self.assertNotIn("DISPATCH_DEADLINE", popen.call_args.kwargs["env"])
        self.assertIsNone(self._last_status().get("deadline"))

    def test_answer_empty_stored_deadline_rejected_as_corrupt(self):
        self._make_prior_status("w-prior-answer", "", with_question=True)
        self._answer_rejected("w-prior-answer", "DEADLINE_MALFORMED")

    def test_continue_stale_controller_env_does_not_bind_child(self):
        self._make_checkpoint("w-prior-ck", None)
        args = SimpleNamespace(worker_id="w-prior-ck", worktree=None,
                               task_file=str(self.brief), executor="fixture")
        with self._patched() as popen, self._env_deadline(VALID_DEADLINE):
            cli.cmd_checkpoint_continue(args)
        popen.assert_called_once()
        self.assertNotIn("DISPATCH_DEADLINE", popen.call_args.kwargs["env"])
        self.assertIsNone(self._last_status().get("deadline"))


class LostLineageAdmissionTests(_IsolatedDispatchRoot):
    """CS red case (missing_lineage_acceptance.py): lost lineage evidence
    must never authorize an unbounded continuation.

    Explicit dispositions stay distinct — an unknown lineage (no readable
    status row, corrupt JSON, or a legacy row written before deadline
    admission that carries no deadline key) rejects before any effect;
    a stored explicit null stays genuinely unbounded.
    """

    def _rewrite_status(self, worker_id, mutate):
        """Apply one mutation to the stored status row on disk."""
        path = status_path(worker_id)
        row = json.loads(path.read_text())
        mutate(row)
        path.write_text(json.dumps(row, indent=2))

    # -- checkpoint continue: the exact reproduced fault and its family --

    def test_continue_missing_prior_status_rejected(self):
        # The CS fault: expired checkpoint lineage, only the owned status
        # row disappears. Continuation must reject, not resume unbounded.
        checkpoint.write_checkpoint_file(
            slug="fixture", phase="1", worker_id="w-lost-status",
            commit_sha="source-revision", directive="pause-for-review")
        self._continue_rejected("w-lost-status", "DEADLINE_LINEAGE_UNKNOWN")

    def test_continue_corrupt_prior_status_rejected(self):
        self._make_checkpoint("w-corrupt-row", VALID_DEADLINE)
        status_path("w-corrupt-row").write_text("{corrupt json")
        self._continue_rejected("w-corrupt-row", "DEADLINE_LINEAGE_UNKNOWN")

    def test_continue_legacy_row_without_deadline_key_rejected(self):
        # A row without a "deadline" key predates deadline admission: unknown
        # metadata, not an explicit unbounded disposition.
        self._make_checkpoint("w-legacy-row", VALID_DEADLINE)
        self._rewrite_status("w-legacy-row", lambda row: row.pop("deadline"))
        self._continue_rejected("w-legacy-row", "DEADLINE_LINEAGE_UNKNOWN")

    # -- answer: same principle across entrypoints --

    def test_answer_legacy_row_without_deadline_key_rejected(self):
        self._make_prior_status("w-legacy-answer", VALID_DEADLINE,
                                with_question=True)
        self._rewrite_status("w-legacy-answer",
                             lambda row: row.pop("deadline"))
        self._answer_rejected("w-legacy-answer", "DEADLINE_LINEAGE_UNKNOWN")

    def test_answer_corrupt_prior_status_rejected(self):
        # read_status conflates corrupt JSON with a missing row, so the
        # pre-existing "no worker" guard (exit 2) rejects first. Either way
        # the corrupt lineage fails closed before any side effect.
        self._make_prior_status("w-corrupt-answer", VALID_DEADLINE,
                                with_question=True)
        status_path("w-corrupt-answer").write_text("{corrupt json")
        with self._patched() as popen, self._stderr() as err:
            with self.assertRaises(SystemExit) as stopped:
                cli.cmd_answer(SimpleNamespace(worker_id="w-corrupt-answer",
                                               answer="the answer",
                                               answer_file=None))
        self.assertEqual(stopped.exception.code, 2)
        self.assertIn("no worker", err.getvalue())
        popen.assert_not_called()
        self.assertFalse((self.root / "tasks").exists(), "no task archive write")
        self.assertFalse((self.root / "questions" / "_resolved").exists(),
                         "question file not resolved")
        self.assertFalse((self.root / "session_registry.jsonl").exists(),
                         "no registry rows")

    def test_answer_missing_worker_rejected(self):
        # Pre-existing disposition, pinned: no row at all is no worker (exit 2),
        # and never a launch.
        with self._patched() as popen, self._stderr() as err:
            with self.assertRaises(SystemExit) as stopped:
                cli.cmd_answer(SimpleNamespace(worker_id="w-never-was",
                                               answer="the answer",
                                               answer_file=None))
        self.assertEqual(stopped.exception.code, 2)
        self.assertIn("no worker", err.getvalue())
        popen.assert_not_called()
        self.assertFalse(any((self.root / "status").glob("*.json")),
                         "no status rows on rejection")

    # -- explicit unbounded stays admitted (the contrast case) --

    def test_continue_explicit_null_deadline_still_launches_unbounded(self):
        self._make_checkpoint("w-null-ck", None)
        args = SimpleNamespace(worker_id="w-null-ck", worktree=None,
                               task_file=str(self.brief), executor="fixture")
        with self._patched() as popen:
            cli.cmd_checkpoint_continue(args)
        popen.assert_called_once()
        self.assertNotIn("DISPATCH_DEADLINE", popen.call_args.kwargs["env"])
        self.assertIsNone(self._last_status().get("deadline"))

    def test_answer_explicit_null_deadline_still_launches_unbounded(self):
        self._make_prior_status("w-null-answer", None)
        with self._patched() as popen:
            cli.cmd_answer(SimpleNamespace(worker_id="w-null-answer",
                                           answer="the answer",
                                           answer_file=None))
        popen.assert_called_once()
        self.assertNotIn("DISPATCH_DEADLINE", popen.call_args.kwargs["env"])
        self.assertIsNone(self._last_status().get("deadline"))


if __name__ == "__main__":
    unittest.main()
