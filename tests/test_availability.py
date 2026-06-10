import os
import tempfile
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
    def setUp(self):
        # Isolate state so resolve()'s cache write never touches the real
        # ~/.local/share/pushing-dispatch/availability.json.
        self.tmp = tempfile.TemporaryDirectory()
        self._prev = os.environ.get("DISPATCH_ROOT")
        os.environ["DISPATCH_ROOT"] = self.tmp.name
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self._restore)

    def _restore(self):
        if self._prev is None:
            os.environ.pop("DISPATCH_ROOT", None)
        else:
            os.environ["DISPATCH_ROOT"] = self._prev

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

    def test_lm_studio_available_from_nuc_local_keychain_slot(self):
        with mock.patch.dict(os.environ, {}, clear=True), \
             mock.patch.object(availability, "_keychain_has", return_value=True):
            self.assertTrue(availability._local_ready("lm-studio"))

    def test_lm_studio_available_from_nucbox_gemma_url(self):
        with mock.patch.dict(os.environ, {"NUCBOX_OLLAMA_OPENAI_BASE_URL": "http://nucbox.example:11434/v1"}, clear=True), \
             mock.patch.object(availability, "_keychain_has", return_value=False):
            self.assertTrue(availability._local_ready("lm-studio"))

if __name__ == "__main__":
    unittest.main()
