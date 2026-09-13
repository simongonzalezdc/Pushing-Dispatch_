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

    def test_stable_checkpoint_identity(self):
        first = workflow_intent.checkpoint_operation_id(b"checkpoint bytes")
        second = workflow_intent.checkpoint_operation_id(b"checkpoint bytes")
        self.assertEqual(first, second)
        self.assertNotEqual(first, workflow_intent.checkpoint_operation_id(b"changed"))

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


if __name__ == "__main__":
    unittest.main()
