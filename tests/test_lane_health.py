import time
import unittest
from unittest import mock
from pathlib import Path
import tempfile

from dispatch_lib import lane_health

class TestClassify(unittest.TestCase):
    def test_classify_auth(self):
        self.assertEqual(lane_health.classify_failure("HTTP 401 Unauthorized"), "auth")
        self.assertEqual(lane_health.classify_failure("token expired"), "auth")

    def test_classify_rate_limit(self):
        self.assertEqual(lane_health.classify_failure("HTTP 429 Too Many Requests"), "rate_limit")

    def test_classify_network(self):
        self.assertEqual(lane_health.classify_failure("Connection timed out"), "network")

    def test_classify_task_default(self):
        self.assertEqual(lane_health.classify_failure("AssertionError in tests"), "task")

class TestCooldown(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "lane_health.json"
        patcher = mock.patch("dispatch_lib.lane_health.lane_health_path", return_value=self.path)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def test_demote_then_in_cooldown(self):
        lane_health.demote("zai-glm", "rate_limit", now=1000.0)
        self.assertTrue(lane_health.in_cooldown("zai-glm", now=1001.0))

    def test_cooldown_expires(self):
        lane_health.demote("zai-glm", "rate_limit", now=1000.0)
        # rate_limit backoff is 60s
        self.assertFalse(lane_health.in_cooldown("zai-glm", now=1000.0 + 61))

    def test_auth_longer_than_rate_limit(self):
        lane_health.demote("kimi-coding", "auth", now=1000.0)
        self.assertTrue(lane_health.in_cooldown("kimi-coding", now=1000.0 + 61))

    def test_recover_clears(self):
        lane_health.demote("zai-glm", "rate_limit", now=1000.0)
        lane_health.recover("zai-glm")
        self.assertFalse(lane_health.in_cooldown("zai-glm", now=1001.0))

if __name__ == "__main__":
    unittest.main()
