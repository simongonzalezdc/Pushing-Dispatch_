import hashlib
import json
import os
import tempfile
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
            workflow_intent.record_launch_intent(operation_id, parameters)
        self.assertEqual(path.read_bytes(), before)
        with self.assertRaises(workflow_intent.IntentConflict):
            workflow_intent.transition(
                operation_id, "launch_not_started", "launch_requested"
            )
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
        workflow_intent.transition(op, "launch_requested", "launch_started", pid=42)
        with self.assertRaisesRegex(workflow_intent.IntentConflict, "reconciliation"):
            workflow_intent.record_launch_intent(op, {"cwd": "/work"})

    def test_changed_parameters_are_rejected(self):
        op = workflow_intent.checkpoint_operation_id(b"two")
        workflow_intent.record_launch_intent(op, {"executor": "a"})
        workflow_intent.transition(op, "launch_requested", "launch_not_started")
        with self.assertRaisesRegex(workflow_intent.IntentConflict, "changed parameters"):
            workflow_intent.record_launch_intent(op, {"executor": "b"})

    def test_authoritative_non_start_can_retry_same_operation(self):
        op = workflow_intent.checkpoint_operation_id(b"three")
        workflow_intent.record_launch_intent(op, {"executor": "a"})
        workflow_intent.transition(op, "launch_requested", "launch_not_started")
        retried = workflow_intent.record_launch_intent(op, {"executor": "a"})
        self.assertEqual(retried["state"], "launch_requested")

    def test_record_is_complete_json_after_each_transition(self):
        op = workflow_intent.checkpoint_operation_id(b"four")
        workflow_intent.record_launch_intent(op, {"executor": "a"})
        workflow_intent.transition(op, "launch_requested", "launch_started", pid=7)
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
        workflow_intent.transition(op, "launch_requested", "launch_not_started")
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
                op, "launch_requested", "launch_started", schema_version=2
            )
        self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
