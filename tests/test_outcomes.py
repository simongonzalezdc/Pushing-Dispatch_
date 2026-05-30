import json
import tempfile
import unittest
from unittest import mock
from pathlib import Path
from dispatch_lib import outcomes

class TestOutcomes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "outcomes.jsonl"
        p = mock.patch("dispatch_lib.outcomes.outcomes_path", return_value=self.path)
        p.start(); self.addCleanup(p.stop); self.addCleanup(self.tmp.cleanup)

    def test_record_appends_jsonl(self):
        outcomes.record("w1", "codex-spark", "hard_task_candidates", "success", 12.5, 0.03)
        outcomes.record("w2", "zai-glm", "standard_candidates", "auth", 1.0, 0.0)
        lines = self.path.read_text().strip().splitlines()
        self.assertEqual(len(lines), 2)
        first = json.loads(lines[0])
        self.assertEqual(first["executor"], "codex-spark")
        self.assertEqual(first["result"], "success")

    def test_success_rate(self):
        outcomes.record("w1", "zai-glm", "standard_candidates", "success", 1, 0)
        outcomes.record("w2", "zai-glm", "standard_candidates", "task", 1, 0)
        self.assertAlmostEqual(outcomes.success_rate("zai-glm"), 0.5)

if __name__ == "__main__":
    unittest.main()
