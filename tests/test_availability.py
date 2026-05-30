import unittest
from unittest import mock

from dispatch_lib import availability

MATRIX = {
    "executors": {
        "opus":        {"provider": "anthropic"},
        "openai-mini": {"provider": "openai-codex"},
        "zai-glm":     {"provider": "zai", "key_env": "Z_AI_API_KEY", "key_account": "z_ai_api_key"},
        "lm-studio":   {"provider": "lm-studio"},
    }
}

class TestAvailability(unittest.TestCase):
    def test_anthropic_available_when_claude_logged_in(self):
        with mock.patch.object(availability, "_anthropic_ready", return_value=True), \
             mock.patch.object(availability, "_codex_ready", return_value=False), \
             mock.patch.object(availability, "_key_present", return_value=False), \
             mock.patch.object(availability, "_local_ready", return_value=False):
            avail = availability.resolve(MATRIX, use_cache=False)
        self.assertTrue(avail["opus"]["available"])
        self.assertFalse(avail["openai-mini"]["available"])

    def test_api_key_provider_available_when_key_present(self):
        with mock.patch.object(availability, "_anthropic_ready", return_value=False), \
             mock.patch.object(availability, "_codex_ready", return_value=False), \
             mock.patch.object(availability, "_key_present", return_value=True), \
             mock.patch.object(availability, "_local_ready", return_value=False):
            avail = availability.resolve(MATRIX, use_cache=False)
        self.assertTrue(avail["zai-glm"]["available"])

    def test_available_set_helper(self):
        with mock.patch.object(availability, "_anthropic_ready", return_value=True), \
             mock.patch.object(availability, "_codex_ready", return_value=True), \
             mock.patch.object(availability, "_key_present", return_value=False), \
             mock.patch.object(availability, "_local_ready", return_value=False):
            s = availability.available_set(MATRIX, use_cache=False)
        self.assertIn("opus", s)
        self.assertIn("openai-mini", s)
        self.assertNotIn("zai-glm", s)

if __name__ == "__main__":
    unittest.main()
