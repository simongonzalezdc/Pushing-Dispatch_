import os
from pathlib import Path
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

    def test_kimi_cli_available_from_oauth_refresh_token(self):
        cred = Path(self.tmp.name) / "kimi-code.json"
        cred.write_text('{"refresh_token": "refresh-token"}')
        with mock.patch.dict(os.environ, {"KIMI_CREDENTIALS_PATH": str(cred)}), \
             mock.patch.object(availability.shutil, "which", return_value="/usr/local/bin/kimi"):
            self.assertTrue(availability._kimi_cli_ready())

    def test_kimi_cli_unavailable_without_cli(self):
        cred = Path(self.tmp.name) / "kimi-code.json"
        cred.write_text('{"refresh_token": "refresh-token"}')
        with mock.patch.dict(os.environ, {"KIMI_CREDENTIALS_PATH": str(cred)}), \
             mock.patch.object(availability.shutil, "which", return_value=None):
            self.assertFalse(availability._kimi_cli_ready())

    def test_kimi_cli_executor_uses_oauth_readiness(self):
        matrix = {"executors": {"kimi-moonshot": {"provider": "kimi-cli"}}}
        with mock.patch.object(availability, "_kimi_cli_ready", return_value=True):
            avail = availability.resolve(matrix, use_cache=False)
        self.assertTrue(avail["kimi-moonshot"]["available"])
        self.assertEqual(avail["kimi-moonshot"]["provider"], "kimi-cli")

    def test_cache_invalidates_when_matrix_auth_shape_changes(self):
        first = {"executors": {"lane": {"provider": "zai", "key_env": "Z_AI_API_KEY"}}}
        second = {"executors": {"lane": {"provider": "kimi-cli", "wrapper": "kimi-cli.sh"}}}

        with mock.patch.object(availability, "_key_present", return_value=False):
            self.assertFalse(availability.resolve(first, use_cache=True)["lane"]["available"])

        with mock.patch.object(availability, "_kimi_cli_ready", return_value=True):
            self.assertTrue(availability.resolve(second, use_cache=True)["lane"]["available"])

if __name__ == "__main__":
    unittest.main()
