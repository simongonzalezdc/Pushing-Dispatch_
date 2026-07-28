import json
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
    def _models_response(self, *model_ids):
        response = mock.MagicMock(status=200)
        response.__enter__.return_value = response
        response.read.return_value = json.dumps({
            "object": "list",
            "data": [{"id": model_id} for model_id in model_ids],
        }).encode()
        return response

    def test_local_models_probe_rejects_declared_model_mismatch(self):
        cfg = {
            "provider": "unsloth-openai",
            "model_id": "qwen3.5-35b-a3b",
            "health_url": "http://nucbox.example/v1/models",
        }
        response = mock.MagicMock(status=200)
        response.__enter__.return_value = response
        response.read.return_value = json.dumps({
            "object": "list",
            "data": [{"id": "unsloth/Qwen3.6-27B-MTP-GGUF"}],
        }).encode()
        with mock.patch(
            "dispatch_lib.availability.urllib.request.urlopen",
            return_value=response,
        ):
            self.assertFalse(availability._executor_available(cfg))

    def test_ollama_catalog_latest_alias_matches_response_model_name(self):
        cfg = {
            "provider": "ollama",
            "model_id": "qwen35-2b-max",
            "health_url": "http://dell.example/v1/models",
        }
        with mock.patch(
            "dispatch_lib.availability.urllib.request.urlopen",
            return_value=self._models_response("qwen35-2b-max:latest"),
        ):
            self.assertTrue(availability._executor_available(cfg))

    def test_local_cascade_requires_exact_validator_model(self):
        cfg = {
            "provider": "ollama",
            "model_id": "qwen35-2b-max",
            "health_url": "http://dell.example/v1/models",
            "validator_model_id": "unsloth/Qwen3.6-27B-MTP-GGUF",
            "validator_health_url": "http://nuc.example/v1/models",
        }
        responses = (
            self._models_response("qwen35-2b-max"),
            self._models_response("wrong-validator"),
        )
        with mock.patch(
            "dispatch_lib.availability.urllib.request.urlopen",
            side_effect=responses,
        ):
            self.assertFalse(availability._executor_available(cfg))

    def test_on_demand_local_lane_uses_exact_activation_baseline(self):
        cfg = {
            "provider": "unsloth-openai",
            "on_demand": True,
            "model_id": "Qwen3.5-35B-A3B-Q4_K_M.gguf",
            "activation_health_url": "http://nuc.example:8892/v1/models",
            "activation_model_id": "unsloth/Qwen3.6-27B-MTP-GGUF",
        }
        with mock.patch(
            "dispatch_lib.availability.urllib.request.urlopen",
            return_value=self._models_response("unsloth/Qwen3.6-27B-MTP-GGUF"),
        ):
            self.assertTrue(availability._executor_available(cfg))

    def test_on_demand_local_lane_rejects_wrong_activation_baseline(self):
        cfg = {
            "provider": "unsloth-openai",
            "on_demand": True,
            "model_id": "qwen3.6:35b",
            "activation_health_url": "http://nuc.example:8892/v1/models",
            "activation_model_id": "unsloth/Qwen3.6-27B-MTP-GGUF",
        }
        with mock.patch(
            "dispatch_lib.availability.urllib.request.urlopen",
            return_value=self._models_response("wrong-model"),
        ):
            self.assertFalse(availability._executor_available(cfg))

    def test_agy_provider_uses_cli_presence(self):
        with mock.patch("dispatch_lib.availability.shutil.which", return_value="/usr/local/bin/agy"):
            self.assertTrue(availability._executor_available({"provider": "agy"}))

    def test_kilo_provider_uses_cli_presence(self):
        with mock.patch("dispatch_lib.availability.shutil.which", return_value="/usr/local/bin/kilo"):
            self.assertTrue(availability._executor_available({"provider": "kilo-cli"}))

    def test_kimi_k3_subscription_uses_cli_presence(self):
        with mock.patch("dispatch_lib.availability.shutil.which", return_value="/usr/local/bin/kimi"):
            self.assertTrue(availability._executor_available({"provider": "kimi-cli"}))

    def test_gjc_provider_uses_cli_presence(self):
        with mock.patch("dispatch_lib.availability.shutil.which", return_value="/usr/local/bin/gjc"):
            self.assertTrue(availability._executor_available({"provider": "gjc"}))

    def test_ollama_cloud_kimi_k3_fails_closed_when_model_is_absent(self):
        cfg = {"provider": "ollama-cloud", "model_id": "kimi-k3", "key_env": "OLLAMA_API_KEY"}
        with mock.patch.object(availability, "_key_present", return_value=True), \
             mock.patch.object(availability, "_load_ollama_cloud_key", return_value="secret"), \
             mock.patch("dispatch_lib.availability.urllib.request.urlopen", side_effect=OSError):
            self.assertFalse(availability._executor_available(cfg))

    def test_ollama_cloud_kimi_k3_is_ready_only_after_live_model_probe(self):
        cfg = {"provider": "ollama-cloud", "model_id": "kimi-k3", "key_env": "OLLAMA_API_KEY"}
        response = mock.MagicMock(status=200)
        response.__enter__.return_value = response
        with mock.patch.object(availability, "_key_present", return_value=True), \
             mock.patch.object(availability, "_load_ollama_cloud_key", return_value="secret"), \
             mock.patch("dispatch_lib.availability.urllib.request.urlopen", return_value=response):
            self.assertTrue(availability._executor_available(cfg))

    def test_grok_provider_uses_cli_presence(self):
        with mock.patch("dispatch_lib.availability.shutil.which", return_value="/usr/local/bin/grok") as which, \
             mock.patch("dispatch_lib.availability.Path.exists", return_value=True):
            self.assertTrue(availability._executor_available({"provider": "grok-cli"}))
        which.assert_called_once_with("grok")

    def test_grok_provider_is_unavailable_without_auth(self):
        with mock.patch.dict(os.environ, {}, clear=True), \
             mock.patch("dispatch_lib.availability.shutil.which", return_value="/usr/local/bin/grok"), \
             mock.patch("dispatch_lib.availability.Path.exists", return_value=False):
            self.assertFalse(availability._executor_available({"provider": "grok-cli"}))

    def test_grok_provider_accepts_api_key_auth(self):
        with mock.patch.dict(os.environ, {"XAI_API_KEY": "present"}, clear=True), \
             mock.patch("dispatch_lib.availability.shutil.which", return_value="/usr/local/bin/grok"):
            self.assertTrue(availability._executor_available({"provider": "grok-cli"}))

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
            self.assertTrue(availability._local_ready("lm-studio", {}))

    def test_lm_studio_available_from_nucbox_gemma_url(self):
        with mock.patch.dict(os.environ, {"NUCBOX_OLLAMA_OPENAI_BASE_URL": "http://nucbox.example:11434/v1"}, clear=True), \
             mock.patch.object(availability, "_keychain_has", return_value=False):
            self.assertTrue(availability._local_ready("lm-studio", {}))

if __name__ == "__main__":
    unittest.main()
