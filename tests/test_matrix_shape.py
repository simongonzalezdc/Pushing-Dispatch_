import unittest
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Providers that authenticate via CLI login or run locally (no API key needed).
CLI_OR_LOCAL = {"anthropic", "openai-codex", "ollama", "lm-studio", "codex-oss"}

class TestMatrixShape(unittest.TestCase):
    def setUp(self):
        with open(ROOT / "dispatch_matrix.toml", "rb") as f:
            self.m = tomllib.load(f)

    def test_auto_route_has_ordered_lists(self):
        ar = self.m["auto_route"]
        for key in ("trivial_candidates", "standard_candidates",
                    "hard_task_candidates", "hard_breakout_candidates",
                    "long_context_candidates", "consult_candidates"):
            self.assertIsInstance(ar[key], list, key)
            self.assertTrue(len(ar[key]) >= 1, key)

    def test_candidates_reference_real_executors(self):
        executors = set(self.m["executors"])
        ar = self.m["auto_route"]
        for key, val in ar.items():
            if key.endswith("_candidates"):
                for ex in val:
                    self.assertIn(ex, executors, f"{key} -> {ex}")

    def test_api_key_executors_have_key_metadata(self):
        for name, cfg in self.m["executors"].items():
            if cfg.get("provider") not in CLI_OR_LOCAL:
                self.assertIn("key_env", cfg, name)
                self.assertIn("key_account", cfg, name)

    def test_openai_executors_have_account_hint(self):
        for name, cfg in self.m["executors"].items():
            if cfg.get("provider") == "openai-codex":
                self.assertIn("account", cfg, name)

    def test_example_matches_live_matrix(self):
        live = (ROOT / "dispatch_matrix.toml").read_bytes()
        example = (ROOT / "dispatch_matrix.toml.example").read_bytes()
        self.assertEqual(live, example, "dispatch_matrix.toml and .example must be identical")

if __name__ == "__main__":
    unittest.main()
