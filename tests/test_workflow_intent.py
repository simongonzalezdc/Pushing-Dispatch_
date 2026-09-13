import hashlib
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from dispatch_lib import workflow_intent


class WorkflowIntentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"DISPATCH_ROOT": self.tmp.name})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def intent_path(self, operation_id):
        return Path(self.tmp.name) / "workflow" / "intents" / f"{operation_id}.json"

    def assert_rejected_unchanged(self, operation_id, content, parameters=None):
        path = self.intent_path(operation_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        before = path.read_bytes()
        parameters = parameters or {"executor": "a"}
        with self.assertRaises(workflow_intent.IntentConflict):
            workflow_intent.record_launch_intent(
                operation_id, parameters, expected_revision=0)
        self.assertEqual(path.read_bytes(), before)
        with self.assertRaises(workflow_intent.IntentConflict):
            workflow_intent.transition(
                operation_id, "launch_not_started", "launch_requested",
                expected_revision=0)
        self.assertEqual(path.read_bytes(), before)

    def test_stable_checkpoint_identity(self):
        first = workflow_intent.checkpoint_operation_id(b"checkpoint bytes")
        second = workflow_intent.checkpoint_operation_id(b"checkpoint bytes")
        self.assertEqual(first, second)
        self.assertNotEqual(first, workflow_intent.checkpoint_operation_id(b"changed"))

    def test_malformed_operation_identity_is_typed_conflict(self):
        with self.assertRaisesRegex(workflow_intent.IntentConflict, "invalid operation_id"):
            workflow_intent.record_launch_intent("../bad", {"cwd": "/work"})

    def test_started_intent_blocks_blind_retry(self):
        op = workflow_intent.checkpoint_operation_id(b"one")
        workflow_intent.record_launch_intent(op, {"cwd": "/work"})
        workflow_intent.transition(
            op, "launch_requested", "launch_started",
            worker_id="w-started", pid=42, expected_revision=0)
        with self.assertRaisesRegex(workflow_intent.IntentConflict, "reconciliation"):
            workflow_intent.record_launch_intent(
                op, {"cwd": "/work"}, expected_revision=1)

    def test_changed_parameters_are_rejected(self):
        op = workflow_intent.checkpoint_operation_id(b"two")
        workflow_intent.record_launch_intent(op, {"executor": "a"})
        workflow_intent.transition(
            op, "launch_requested", "launch_not_started",
            worker_id="w-failed", expected_revision=0)
        with self.assertRaisesRegex(workflow_intent.IntentConflict, "changed parameters"):
            workflow_intent.record_launch_intent(
                op, {"executor": "b"}, expected_revision=1)

    def test_authoritative_non_start_can_retry_same_operation(self):
        op = workflow_intent.checkpoint_operation_id(b"three")
        workflow_intent.record_launch_intent(op, {"executor": "a"})
        workflow_intent.transition(
            op, "launch_requested", "launch_not_started",
            worker_id="w-failed", expected_revision=0)
        retried = workflow_intent.record_launch_intent(
            op, {"executor": "a"}, expected_revision=1)
        self.assertEqual(retried["state"], "launch_requested")
        self.assertNotIn("worker_id", retried)

    def test_retry_without_current_revision_rejected(self):
        op = workflow_intent.checkpoint_operation_id(b"three-nocas")
        workflow_intent.record_launch_intent(op, {"executor": "a"})
        workflow_intent.transition(
            op, "launch_requested", "launch_not_started",
            worker_id="w-failed", expected_revision=0)
        with self.assertRaisesRegex(workflow_intent.IntentConflict,
                                    "expected_revision required"):
            workflow_intent.record_launch_intent(op, {"executor": "a"})

    def test_record_is_complete_json_after_each_transition(self):
        op = workflow_intent.checkpoint_operation_id(b"four")
        workflow_intent.record_launch_intent(op, {"executor": "a"})
        workflow_intent.transition(
            op, "launch_requested", "launch_started",
            worker_id="w-started", pid=7, expected_revision=0)
        path = Path(self.tmp.name) / "workflow" / "intents" / f"{op}.json"
        record = json.loads(path.read_text())
        self.assertEqual(record["state"], "launch_started")
        self.assertEqual(record["pid"], 7)
        self.assertEqual(record["parameters"], {"executor": "a"})

    def test_partial_non_started_record_cannot_be_rewritten(self):
        op = workflow_intent.checkpoint_operation_id(b"partial")
        parameters = {"executor": "a"}
        digest = hashlib.sha256(
            json.dumps(parameters, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        partial = json.dumps({
            "parameters_sha256": digest,
            "state": "launch_not_started",
        }).encode()
        self.assert_rejected_unchanged(op, partial, parameters)

    def test_malformed_existing_records_fail_closed(self):
        op = workflow_intent.checkpoint_operation_id(b"malformed variants")
        workflow_intent.record_launch_intent(op, {"executor": "a"})
        workflow_intent.transition(
            op, "launch_requested", "launch_not_started",
            worker_id="w-failed", expected_revision=0)
        valid = json.loads(self.intent_path(op).read_text())
        variants = {
            "wrong schema": {**valid, "schema_version": 2},
            "wrong operation": {**valid, "operation_id": op + "-other"},
            "parameters disagree with digest": {
                **valid, "parameters": {"executor": "b"}
            },
            "invalid state": {**valid, "state": 7},
            "invalid created timestamp": {**valid, "created_at_ns": True},
            "reversed timestamps": {
                **valid, "updated_at_ns": valid["created_at_ns"] - 1
            },
            "unknown schema field": {**valid, "unexpected": "value"},
        }
        for label, record in variants.items():
            with self.subTest(label=label):
                self.assert_rejected_unchanged(
                    op,
                    json.dumps(record, sort_keys=True).encode(),
                )

    def test_corrupt_json_is_typed_conflict_and_unchanged(self):
        op = workflow_intent.checkpoint_operation_id(b"corrupt")
        self.assert_rejected_unchanged(op, b'{"schema_version":')

    def test_transition_cannot_overwrite_identity_fields(self):
        op = workflow_intent.checkpoint_operation_id(b"immutable")
        workflow_intent.record_launch_intent(op, {"executor": "a"})
        path = self.intent_path(op)
        before = path.read_bytes()
        with self.assertRaisesRegex(
            workflow_intent.IntentConflict, "transition fields"
        ):
            workflow_intent.transition(
                op, "launch_requested", "launch_started",
                schema_version=2, expected_revision=0)
        self.assertEqual(path.read_bytes(), before)

    def test_cross_state_effect_fields_fail_closed(self):
        op = workflow_intent.checkpoint_operation_id(b"cross-state fields")
        workflow_intent.record_launch_intent(op, {"executor": "a"})
        requested = json.loads(self.intent_path(op).read_text())
        variants = {
            "requested worker": {**requested, "worker_id": "w-stale"},
            "requested pid": {**requested, "pid": 43210},
            "non-started missing worker": {
                **requested, "state": "launch_not_started"
            },
            "non-started with pid": {
                **requested,
                "state": "launch_not_started",
                "worker_id": "w-failed",
                "pid": 43210,
            },
            "started missing worker": {
                **requested, "state": "launch_started", "pid": 43210
            },
            "started missing pid": {
                **requested,
                "state": "launch_started",
                "worker_id": "w-started",
            },
            "started empty worker": {
                **requested,
                "state": "launch_started",
                "worker_id": "",
                "pid": 43210,
            },
        }
        for label, record in variants.items():
            with self.subTest(label=label):
                self.assert_rejected_unchanged(
                    op, json.dumps(record, sort_keys=True).encode()
                )

    def test_transition_rejects_incomplete_target_state_without_write(self):
        op = workflow_intent.checkpoint_operation_id(b"target fields")
        workflow_intent.record_launch_intent(op, {"executor": "a"})
        path = self.intent_path(op)
        before = path.read_bytes()
        with self.assertRaisesRegex(
            workflow_intent.IntentConflict, "fields inconsistent with state"
        ):
            workflow_intent.transition(
                op, "launch_requested", "launch_started", expected_revision=0)
        self.assertEqual(path.read_bytes(), before)


class IntentIdentityBoundaryTests(unittest.TestCase):
    """Authoritative identity at the mutation boundary.

    Pins the adapted CS identity regression (immutable started attempt) AND
    the three measured CS counterexamples against snapshot 5d0eae7d:
    omitted-CAS takeover reclamation, two admitted replacements of one
    uncertain original, and the same-destination replacement collision.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"DISPATCH_ROOT": self.tmp.name})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def intent_path(self, operation_id):
        return Path(self.tmp.name) / "workflow" / "intents" / f"{operation_id}.json"

    def _conflict_unchanged(self, operation_id, callable_, label):
        path = self.intent_path(operation_id)
        before = path.read_bytes()
        with self.assertRaises(workflow_intent.IntentConflict, msg=label):
            callable_()
        self.assertEqual(path.read_bytes(), before, label)

    def _make_started(self, op, worker="worker-original", pid=12345,
                      token="controller-a"):
        workflow_intent.record_launch_intent(
            op, {"task": "synthetic-owned-probe"}, controller_token=token)
        return workflow_intent.transition(
            op, "launch_requested", "launch_started",
            worker_id=worker, pid=pid, controller_token=token,
            expected_revision=0)

    # -- the adapted CS probe regression --

    def test_started_identity_rewrite_rejected_bytes_unchanged(self):
        op = workflow_intent.checkpoint_operation_id(b"rewrite")
        self._make_started(op)
        self._conflict_unchanged(
            op,
            lambda: workflow_intent.transition(
                op, "launch_started", "launch_started",
                worker_id="worker-replacement", pid=23456,
                controller_token="controller-a", expected_revision=1),
            "started attempt identity must be immutable")

    def test_started_idempotent_replay_allowed_without_mutation(self):
        op = workflow_intent.checkpoint_operation_id(b"replay")
        self._make_started(op)
        before = self.intent_path(op).read_bytes()
        record = workflow_intent.transition(
            op, "launch_started", "launch_started",
            worker_id="worker-original", pid=12345,
            controller_token="controller-a", expected_revision=1)
        self.assertEqual(record["state"], "launch_started")
        self.assertEqual(self.intent_path(op).read_bytes(), before,
                         "identical replay must not mutate the record")

    def test_transition_without_cas_rejected(self):
        op = workflow_intent.checkpoint_operation_id(b"cas-required")
        workflow_intent.record_launch_intent(
            op, {"task": "x"}, controller_token="controller-a")
        self._conflict_unchanged(
            op,
            lambda: workflow_intent.transition(
                op, "launch_requested", "launch_started",
                worker_id="w", pid=1, controller_token="controller-a"),
            "omitted expected_revision must never bypass fencing")

    def test_started_cannot_downgrade_to_not_started(self):
        op = workflow_intent.checkpoint_operation_id(b"downgrade")
        self._make_started(op)
        self._conflict_unchanged(
            op,
            lambda: workflow_intent.transition(
                op, "launch_started", "launch_not_started",
                controller_token="controller-a", expected_revision=1),
            "launched uncertainty must be preserved, never downgraded")

    def test_not_started_worker_cannot_be_rewritten_on_start(self):
        op = workflow_intent.checkpoint_operation_id(b"rewrite-prestart")
        workflow_intent.record_launch_intent(op, {"task": "x"})
        workflow_intent.transition(
            op, "launch_requested", "launch_not_started",
            worker_id="w-first-attempt", expected_revision=0)
        self._conflict_unchanged(
            op,
            lambda: workflow_intent.transition(
                op, "launch_not_started", "launch_started",
                worker_id="w-second-attempt", pid=99, expected_revision=1),
            "recorded worker_id cannot be replaced in place")

    def test_not_started_to_started_keeps_recorded_worker(self):
        op = workflow_intent.checkpoint_operation_id(b"prestart-start")
        workflow_intent.record_launch_intent(op, {"task": "x"})
        workflow_intent.transition(
            op, "launch_requested", "launch_not_started",
            worker_id="w-attempt", expected_revision=0)
        record = workflow_intent.transition(
            op, "launch_not_started", "launch_started",
            worker_id="w-attempt", pid=5, expected_revision=1)
        self.assertEqual(record["worker_id"], "w-attempt")
        self.assertEqual(record["pid"], 5)

    # -- CS counterexample 1: omitted CAS cannot reclaim after takeover --

    def test_stale_controller_cannot_reclaim_after_takeover(self):
        op = workflow_intent.checkpoint_operation_id(b"takeover")
        workflow_intent.record_launch_intent(
            op, {"task": "x"}, controller_token="controller-a")  # rev 0, token A
        # B takes over with the current revision: rev 1, token B.
        workflow_intent.transition(
            op, "launch_requested", "launch_requested",
            controller_token="controller-b", expected_revision=0)
        # Stale A, CAS omitted: typed rejection, bytes unchanged.
        self._conflict_unchanged(
            op,
            lambda: workflow_intent.transition(
                op, "launch_requested", "launch_requested",
                controller_token="controller-a"),
            "omitted CAS cannot bypass takeover fencing")
        # Stale A, stale CAS: rejection, bytes unchanged.
        self._conflict_unchanged(
            op,
            lambda: workflow_intent.transition(
                op, "launch_requested", "launch_requested",
                controller_token="controller-a", expected_revision=0),
            "stale CAS cannot bypass takeover fencing")
        # A cannot reach launch_started under any stale presentation.
        for cas in (workflow_intent._UNSET, 0):
            with self.assertRaises(workflow_intent.IntentConflict,
                                   msg="stale A must not launch after B takeover"):
                workflow_intent.transition(
                    op, "launch_requested", "launch_started",
                    worker_id="w-a", pid=111, controller_token="controller-a",
                    expected_revision=cas)
        record = json.loads(self.intent_path(op).read_text())
        self.assertEqual(record["state"], "launch_requested")
        self.assertEqual(record["controller_token"], "controller-b")

    def test_stale_retry_cannot_reclaim_after_takeover(self):
        op = workflow_intent.checkpoint_operation_id(b"takeover-retry")
        workflow_intent.record_launch_intent(
            op, {"task": "x"}, controller_token="controller-a")
        workflow_intent.transition(
            op, "launch_requested", "launch_not_started",
            worker_id="w-failed", controller_token="controller-a",
            expected_revision=0)
        # B retries with current revision (rev 1): token rebinds to B, rev 2.
        workflow_intent.record_launch_intent(
            op, {"task": "x"}, controller_token="controller-b",
            expected_revision=1)
        # Stale A retry with the revision A knows (0) — and with none.
        for cas in (workflow_intent._UNSET, 0):
            with self.assertRaises(workflow_intent.IntentConflict,
                                   msg="stale A retry must reject"):
                workflow_intent.record_launch_intent(
                    op, {"task": "x"}, controller_token="controller-a",
                    expected_revision=cas)
        record = json.loads(self.intent_path(op).read_text())
        self.assertEqual(record["controller_token"], "controller-b")
        self.assertEqual(record["revision"], 2)

    # -- controller token fencing --

    def test_wrong_token_rejected_at_effect_boundary(self):
        op = workflow_intent.checkpoint_operation_id(b"token-boundary")
        workflow_intent.record_launch_intent(
            op, {"task": "x"}, controller_token="controller-a")
        self._conflict_unchanged(
            op,
            lambda: workflow_intent.transition(
                op, "launch_requested", "launch_started",
                worker_id="w", pid=1, controller_token="controller-b",
                expected_revision=0),
            "effect boundary requires the binding controller")

    def test_correct_token_starts_and_binds(self):
        op = workflow_intent.checkpoint_operation_id(b"token-start")
        workflow_intent.record_launch_intent(
            op, {"task": "x"}, controller_token="controller-a")
        record = workflow_intent.transition(
            op, "launch_requested", "launch_started",
            worker_id="w", pid=1, controller_token="controller-a",
            expected_revision=0)
        self.assertEqual(record["controller_token"], "controller-a")

    def test_legacy_record_adopts_token_at_effect_boundary(self):
        op = workflow_intent.checkpoint_operation_id(b"token-legacy")
        workflow_intent.record_launch_intent(op, {"task": "legacy"})
        record = workflow_intent.transition(
            op, "launch_requested", "launch_started",
            worker_id="w", pid=2, controller_token="controller-new",
            expected_revision=0)
        self.assertEqual(record["controller_token"], "controller-new")
        self._conflict_unchanged(
            op,
            lambda: workflow_intent.transition(
                op, "launch_started", "launch_started",
                worker_id="w", pid=2, controller_token="controller-other",
                expected_revision=1),
            "after adoption the token is bound")

    def test_tokenless_caller_rejected_on_bound_started_record(self):
        op = workflow_intent.checkpoint_operation_id(b"token-required")
        self._make_started(op)
        self._conflict_unchanged(
            op,
            lambda: workflow_intent.transition(
                op, "launch_started", "launch_started",
                worker_id="worker-original", pid=12345, expected_revision=1),
            "post-effect mutations must present the controller token")

    # -- revision (optimistic concurrency for delayed writers) --

    def test_stale_expected_revision_rejected(self):
        op = workflow_intent.checkpoint_operation_id(b"revision")
        self._make_started(op)  # revision is now 1
        self._conflict_unchanged(
            op,
            lambda: workflow_intent.transition(
                op, "launch_started", "launch_started",
                worker_id="worker-original", pid=12345,
                controller_token="controller-a", expected_revision=0),
            "delayed writer holding revision 0 must reject")

    def test_retry_rebinds_token_and_bumps_revision(self):
        op = workflow_intent.checkpoint_operation_id(b"retry-rebind")
        workflow_intent.record_launch_intent(
            op, {"task": "x"}, controller_token="controller-a")
        workflow_intent.transition(
            op, "launch_requested", "launch_not_started",
            worker_id="w-failed", controller_token="controller-a",
            expected_revision=0)
        retried = workflow_intent.record_launch_intent(
            op, {"task": "x"}, controller_token="controller-b",
            expected_revision=1)
        self.assertEqual(retried["state"], "launch_requested")
        self.assertEqual(retried["controller_token"], "controller-b")
        self.assertEqual(retried["revision"], 2)
        record = workflow_intent.transition(
            op, "launch_requested", "launch_started",
            worker_id="w-fresh", pid=8, controller_token="controller-b",
            expected_revision=2)
        self.assertEqual(record["revision"], 3)

    # -- CS counterexample 2: one admitted replacement per uncertain original --

    def test_second_distinct_replacement_of_same_original_rejected(self):
        op = workflow_intent.checkpoint_operation_id(b"replace-src")
        self._make_started(op)
        workflow_intent.record_replacement_intent(
            op, workflow_intent.checkpoint_operation_id(b"replace-one"),
            {"task": "reconciled"}, controller_token="controller-b",
            expected_revision=1)
        original_before = self.intent_path(op).read_bytes()
        with self.assertRaisesRegex(workflow_intent.IntentConflict,
                                    "already admitted replacement"):
            workflow_intent.record_replacement_intent(
                op, workflow_intent.checkpoint_operation_id(b"replace-two"),
                {"task": "reconciled-2"}, controller_token="controller-b",
                expected_revision=2)
        self.assertEqual(self.intent_path(op).read_bytes(), original_before)
        # Neither duplicate may launch: only the admitted replacement exists.
        self.assertFalse(self.intent_path(
            workflow_intent.checkpoint_operation_id(b"replace-two")).exists())

    def test_admitted_replacement_cannot_be_replaced_by_replay_trick(self):
        # Even re-admitting the SAME replacement id with different parameters
        # under the winner is the reused-identity rejection.
        op = workflow_intent.checkpoint_operation_id(b"replace-same")
        replacement_op = workflow_intent.checkpoint_operation_id(b"replace-same-new")
        self._make_started(op)
        workflow_intent.record_replacement_intent(
            op, replacement_op, {"task": "params-a"},
            controller_token="controller-b", expected_revision=1)
        with self.assertRaisesRegex(workflow_intent.IntentConflict, "reused"):
            workflow_intent.record_replacement_intent(
                op, replacement_op, {"task": "params-b"},
                controller_token="controller-b", expected_revision=2)

    def test_replacement_admission_marks_original_and_retains_state(self):
        op = workflow_intent.checkpoint_operation_id(b"replace-mark")
        replacement_op = workflow_intent.checkpoint_operation_id(b"replace-mark-new")
        self._make_started(op)
        replacement = workflow_intent.record_replacement_intent(
            op, replacement_op, {"task": "x"},
            controller_token="controller-b", expected_revision=1)
        original = json.loads(self.intent_path(op).read_text())
        self.assertEqual(original["state"], "launch_started",
                         "uncertainty of the original effect is preserved")
        self.assertEqual(original["worker_id"], "worker-original")
        self.assertEqual(original["pid"], 12345)
        self.assertEqual(original["replaced_by"], replacement_op)
        self.assertEqual(original["revision"], 2)
        self.assertEqual(replacement["state"], "launch_requested")
        self.assertEqual(replacement["attempt"], 2)
        self.assertEqual(replacement["replacement_of"], op)

    def test_replay_completes_lost_admission_mark(self):
        # Crash after mint, before the original's admission mark: a retry
        # finds the existing destination and completes the mark.
        op = workflow_intent.checkpoint_operation_id(b"replace-crash")
        replacement_op = workflow_intent.checkpoint_operation_id(b"replace-crash-new")
        self._make_started(op)
        workflow_intent.record_replacement_intent(
            op, replacement_op, {"task": "x"},
            controller_token="controller-b", expected_revision=1)
        original = json.loads(self.intent_path(op).read_text())
        del original["replaced_by"]  # simulate the lost mark
        original["revision"] = original["revision"] - 1
        self.intent_path(op).write_text(json.dumps(original))
        replacement = workflow_intent.record_replacement_intent(
            op, replacement_op, {"task": "x"},
            controller_token="controller-b",
            expected_revision=original["revision"])
        self.assertEqual(replacement["operation_id"], replacement_op)
        self.assertEqual(
            json.loads(self.intent_path(op).read_text())["replaced_by"],
            replacement_op)

    def _fail_original_mark(self, original_op, marked_by):
        real_write = workflow_intent._write

        def failing_write(path, record):
            if (record.get("operation_id") == original_op
                    and record.get("replaced_by") == marked_by):
                raise OSError("synthetic failure after replacement persisted")
            real_write(path, record)

        return failing_write

    def test_interrupted_completion_cannot_admit_alternate_replacement(self):
        # Fault between the two writes (destination persisted, original's
        # mark lost): a DIFFERENT replacement id must reject without any
        # write. The minted destination is the durable reservation.
        op = workflow_intent.checkpoint_operation_id(b"replace-partial-src")
        first = workflow_intent.checkpoint_operation_id(b"replace-partial-one")
        second = workflow_intent.checkpoint_operation_id(b"replace-partial-two")
        self._make_started(op)
        with mock.patch.object(workflow_intent, "_write",
                               self._fail_original_mark(op, first)):
            with self.assertRaises(OSError):
                workflow_intent.record_replacement_intent(
                    op, first, {"task": "x"},
                    controller_token="controller-b", expected_revision=1)
        self.assertTrue(self.intent_path(first).exists(),
                        "fault seam not reached")
        original_before = self.intent_path(op).read_bytes()
        first_before = self.intent_path(first).read_bytes()
        with self.assertRaisesRegex(workflow_intent.IntentConflict,
                                    "minted replacement attempt"):
            workflow_intent.record_replacement_intent(
                op, second, {"task": "x"},
                controller_token="controller-b", expected_revision=1)
        self.assertEqual(self.intent_path(op).read_bytes(), original_before)
        self.assertEqual(self.intent_path(first).read_bytes(), first_before)
        self.assertFalse(self.intent_path(second).exists())

    def test_interrupted_completion_same_id_retry_completes_idempotently(self):
        # Recovery for the SAME id completes the lost mark without
        # rewriting the destination record, and a further identical retry
        # is a no-op (no second revision bump).
        op = workflow_intent.checkpoint_operation_id(b"replace-partial-rc")
        replacement = workflow_intent.checkpoint_operation_id(b"replace-partial-rc-new")
        self._make_started(op)
        with mock.patch.object(workflow_intent, "_write",
                               self._fail_original_mark(op, replacement)):
            with self.assertRaises(OSError):
                workflow_intent.record_replacement_intent(
                    op, replacement, {"task": "x"},
                    controller_token="controller-b", expected_revision=1)
        destination_before = self.intent_path(replacement).read_bytes()
        recovered = workflow_intent.record_replacement_intent(
            op, replacement, {"task": "x"},
            controller_token="controller-b", expected_revision=1)
        self.assertEqual(self.intent_path(replacement).read_bytes(),
                         destination_before,
                         "recovery must not rewrite the minted destination")
        self.assertEqual(recovered["operation_id"], replacement)
        original = json.loads(self.intent_path(op).read_text())
        self.assertEqual(original["replaced_by"], replacement)
        self.assertEqual(original["revision"], 2)
        replay = workflow_intent.record_replacement_intent(
            op, replacement, {"task": "x"},
            controller_token="controller-b", expected_revision=2)
        self.assertEqual(json.loads(self.intent_path(op).read_text()),
                         original, "identical retry must be a no-op")
        self.assertEqual(replay["revision"],
                         json.loads(self.intent_path(replacement).read_text())["revision"])

    def test_replacement_scan_fails_closed_on_corrupt_store_record(self):
        # An unreadable record in the store must not authorize admission:
        # the scan cannot prove the original unlinked, so it rejects.
        op = workflow_intent.checkpoint_operation_id(b"replace-scan-src")
        replacement = workflow_intent.checkpoint_operation_id(b"replace-scan-new")
        self._make_started(op)
        corrupt = self.intent_path(
            workflow_intent.checkpoint_operation_id(b"replace-scan-other"))
        corrupt.parent.mkdir(parents=True, exist_ok=True)
        corrupt.write_bytes(b"{not json")
        with self.assertRaisesRegex(workflow_intent.IntentConflict,
                                    "unreadable intent record"):
            workflow_intent.record_replacement_intent(
                op, replacement, {"task": "x"},
                controller_token="controller-b", expected_revision=1)
        self.assertFalse(self.intent_path(replacement).exists())

    def test_replacement_requires_started_original_and_cas(self):
        op = workflow_intent.checkpoint_operation_id(b"replace-prestart")
        workflow_intent.record_launch_intent(op, {"task": "x"})
        with self.assertRaisesRegex(workflow_intent.IntentConflict,
                                    "uncertain launched operation"):
            workflow_intent.record_replacement_intent(
                op, workflow_intent.checkpoint_operation_id(b"replace-x"),
                {"task": "x"}, controller_token="controller-a",
                expected_revision=0)
        with self.assertRaisesRegex(workflow_intent.IntentConflict,
                                    "expected_revision required"):
            workflow_intent.record_replacement_intent(
                op, workflow_intent.checkpoint_operation_id(b"replace-y"),
                {"task": "x"}, controller_token="controller-a")
        with self.assertRaisesRegex(workflow_intent.IntentConflict,
                                    "controller token"):
            workflow_intent.record_replacement_intent(
                op, workflow_intent.checkpoint_operation_id(b"replace-u2"),
                {"task": "x"}, controller_token=None, expected_revision=0)

    # -- CS counterexample 3: same destination id, two distinct originals --

    def test_concurrent_same_replacement_id_from_distinct_originals(self):
        op1 = workflow_intent.checkpoint_operation_id(b"collide-orig-1")
        op2 = workflow_intent.checkpoint_operation_id(b"collide-orig-2")
        self._make_started(op1, worker="worker-one", pid=11)
        self._make_started(op2, worker="worker-two", pid=22)
        shared = workflow_intent.checkpoint_operation_id(b"collide-shared")

        results = {}
        barrier = threading.Barrier(2)

        def admit(original, params, worker):
            barrier.wait()  # both pass their pre-lock reads together
            try:
                workflow_intent.record_replacement_intent(
                    original, shared, params, controller_token="controller-r",
                    expected_revision=1)
                results[original] = "ok"
            except workflow_intent.IntentConflict as exc:
                results[original] = str(exc)

        threads = [
            threading.Thread(target=admit, args=(op1, {"task": "a"}, "w-a")),
            threading.Thread(target=admit, args=(op2, {"task": "b"}, "w-b")),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        self.assertFalse(any(t.is_alive() for t in threads))

        outcomes = sorted(results.values())
        self.assertEqual(len([o for o in outcomes if o == "ok"]), 1,
                         "exactly one admission may win")
        loser_msg = next(o for o in outcomes if o != "ok")
        self.assertIn("reused", loser_msg)
        # The winner's acknowledged destination bytes are intact, linked to
        # the winner, and the loser's original was never marked replaced.
        record = json.loads(self.intent_path(shared).read_text())
        winner = op1 if results[op1] == "ok" else op2
        self.assertEqual(record["replacement_of"], winner)
        self.assertEqual(
            json.loads(self.intent_path(winner).read_text())["replaced_by"],
            shared)
        loser = op2 if winner == op1 else op1
        self.assertNotIn("replaced_by",
                         json.loads(self.intent_path(loser).read_text()))

    def test_chained_replacement_increments_attempt(self):
        op1 = workflow_intent.checkpoint_operation_id(b"chain-1")
        self._make_started(op1)
        op2 = workflow_intent.checkpoint_operation_id(b"chain-2")
        workflow_intent.record_replacement_intent(
            op1, op2, {"task": "x"}, controller_token="controller-b",
            expected_revision=1)
        workflow_intent.transition(
            op2, "launch_requested", "launch_started",
            worker_id="w-chain-2", pid=11, controller_token="controller-b",
            expected_revision=0)
        op3 = workflow_intent.checkpoint_operation_id(b"chain-3")
        third = workflow_intent.record_replacement_intent(
            op2, op3, {"task": "x"}, controller_token="controller-c",
            expected_revision=1)
        self.assertEqual(third["attempt"], 3)
        self.assertEqual(third["replacement_of"], op2)
        self.assertEqual(
            json.loads(self.intent_path(op1).read_text())["attempt"], 1)

    def test_read_intent_returns_current_revision(self):
        op = workflow_intent.checkpoint_operation_id(b"read-intent")
        self.assertIsNone(workflow_intent.read_intent(op))
        self._make_started(op)
        record = workflow_intent.read_intent(op)
        self.assertEqual(record["revision"], 1)
        self.assertEqual(record["state"], "launch_started")


class OldReaderCompatibilityTests(unittest.TestCase):
    """Dual-direction reader compatibility (CS measured correction).

    The installed ed27d1fa reader rejects ANY key outside its fixed key set:
    new-reader/old-record compatibility does NOT imply old-reader/new-record
    compatibility. These tests pin both directions with an exact replica of
    the installed validator's schema check (fixed key set, required = keys
    minus worker_id/pid, schema_version == 1).
    """

    OLD_RECORD_KEYS = {
        "schema_version", "operation_id", "parameters", "parameters_sha256",
        "state", "created_at_ns", "updated_at_ns", "worker_id", "pid",
    }
    NEW_FIELDS = ["revision", "controller_token", "attempt",
                  "replacement_of", "replaced_by"]

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"DISPATCH_ROOT": self.tmp.name})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    @staticmethod
    def _old_reader_accepts(record):
        """Exact replica of installed ed27d1fa _validate_record's schema gate."""
        if not isinstance(record, dict) or set(record) - OldReaderCompatibilityTests.OLD_RECORD_KEYS:
            return False
        required = OldReaderCompatibilityTests.OLD_RECORD_KEYS - {"worker_id", "pid"}
        return required.issubset(record)

    def _legacy_record(self, state="launch_requested"):
        parameters = {"executor": "a"}
        return {
            "schema_version": 1,
            "operation_id": "op-legacy-record",
            "parameters": parameters,
            "parameters_sha256": hashlib.sha256(json.dumps(
                parameters, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
            "state": state,
            "created_at_ns": 1,
            "updated_at_ns": 1,
        }

    def test_new_reader_reads_old_record(self):
        path = Path(self.tmp.name) / "workflow" / "intents" / "op-legacy-record.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self._legacy_record()))
        record = workflow_intent.read_intent("op-legacy-record")
        self.assertEqual(record["state"], "launch_requested")

    def test_new_reader_adopts_old_record_through_started(self):
        path = Path(self.tmp.name) / "workflow" / "intents" / "op-legacy-record.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self._legacy_record()))
        record = workflow_intent.transition(
            "op-legacy-record", "launch_requested", "launch_started",
            worker_id="w-legacy", pid=3, controller_token="controller-new",
            expected_revision=0)
        self.assertEqual(record["state"], "launch_started")
        self.assertEqual(record["controller_token"], "controller-new")

    def test_old_reader_rejects_every_new_field(self):
        base = self._legacy_record()
        self.assertTrue(self._old_reader_accepts(base))
        for field in self.NEW_FIELDS:
            with self.subTest(field=field):
                value = {"revision": 0, "attempt": 1,
                         "controller_token": "t",
                         "replacement_of": "op-legacy-record-x",
                         "replaced_by": "op-legacy-record-x"}[field]
                self.assertFalse(
                    self._old_reader_accepts({**base, field: value}),
                    "installed old reader must reject the new authoritative field")

    def test_old_reader_rejects_new_started_record(self):
        # A started record with attempt/revision/token is unreadable for the
        # installed reader: fail-closed, never silently downgraded.
        started = {
            **self._legacy_record(state="launch_started"),
            "worker_id": "w", "pid": 5,
            "revision": 1, "attempt": 1, "controller_token": "t",
        }
        self.assertFalse(self._old_reader_accepts(started))


if __name__ == "__main__":
    unittest.main()
