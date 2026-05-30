import unittest
from unittest import mock
from dispatch_lib import availability, lane_health

class TestDoctorData(unittest.TestCase):
    def test_build_doctor_rows(self):
        from cli import _doctor_rows  # function added in this task
        matrix = {"executors": {
            "opus": {"provider": "anthropic"},
            "zai-glm": {"provider": "zai", "key_env": "Z_AI_API_KEY", "key_account": "z_ai_api_key"},
        }}
        with mock.patch.object(availability, "resolve", return_value={
                 "opus": {"available": True, "provider": "anthropic"},
                 "zai-glm": {"available": False, "provider": "zai"}}), \
             mock.patch.object(lane_health, "in_cooldown", return_value=False), \
             mock.patch.object(lane_health, "needs_relogin", return_value=[]):
            rows = _doctor_rows(matrix)
        by = {r["executor"]: r for r in rows}
        self.assertTrue(by["opus"]["available"])
        self.assertFalse(by["zai-glm"]["available"])

if __name__ == "__main__":
    unittest.main()
