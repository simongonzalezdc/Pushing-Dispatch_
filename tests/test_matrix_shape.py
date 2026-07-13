import unittest
import tomllib
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Providers that authenticate via CLI login or run locally (no API key needed).
CLI_OR_LOCAL = {"anthropic", "openai-codex", "agy", "gjc", "kilo-cli", "kimi-cli", "ollama", "lm-studio"}

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

    def test_codex_subscription_uses_only_gpt56_family(self):
        codex = {
            name: cfg for name, cfg in self.m["executors"].items()
            if cfg.get("provider") == "openai-codex"
        }
        self.assertEqual(set(codex), {"codex-luna", "codex-terra", "codex-sol"})
        self.assertEqual(
            {cfg["model_id"] for cfg in codex.values()},
            {"gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol"},
        )
        serialized = str(self.m).lower()
        self.assertNotIn("gpt-5.5", serialized)
        self.assertNotIn("codex-oss", serialized)
        self.assertNotIn("nucbox", serialized)

    def test_codex_reasoning_policy_prefers_luna_then_terra(self):
        executors = self.m["executors"]
        self.assertEqual(executors["codex-luna"]["reasoning_effort"], "xhigh")
        self.assertEqual(executors["codex-terra"]["reasoning_effort"], "high")
        self.assertEqual(executors["codex-sol"]["reasoning_effort"], "low")

        ar = self.m["auto_route"]
        for key in (
            "trivial_candidates", "standard_candidates", "hard_task_candidates",
            "hard_breakout_candidates", "long_context_candidates",
            "consult_candidates",
        ):
            candidates = ar[key]
            self.assertLess(candidates.index("codex-luna"), candidates.index("codex-terra"), key)
            self.assertLess(candidates.index("codex-terra"), candidates.index("codex-sol"), key)

        self.assertIn("breakout", executors["codex-luna"]["allowed_modes"])

    def test_sol_wrapper_enforces_high_ceiling(self):
        wrapper = ROOT / "bin" / "wrappers" / "codex-sol.sh"
        env = os.environ.copy()
        env["CODEX_REASONING_EFFORT"] = "xhigh"
        result = subprocess.run(
            [str(wrapper), "--help"], env=env, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("capped at high", result.stderr)

    def test_worker_prompt_has_bounded_reasoning_stop_contract(self):
        prompt = (ROOT / "bin" / "wrappers" / "executor_prompt.md").read_text()
        self.assertIn("Stop conditions", prompt)
        self.assertIn("Do not continue reasoning", prompt)
        self.assertIn("reassess", prompt.lower())

    def test_agent_docs_do_not_teach_retired_terra_default(self):
        paths = (
            ROOT / "AGENTS.md",
            ROOT / "GLOBAL_AGENT_ROUTING.md",
            ROOT / "docs" / "PROVIDERS.md",
            ROOT / "docs" / "ORCHESTRATING.md",
            ROOT / "dispatch_packs" / "orchestrator-protocol.md",
        )
        stale = ("Luna for trivial", "Terra is the normal default", "Terra as the everyday default")
        for path in paths:
            text = path.read_text()
            for phrase in stale:
                self.assertNotIn(phrase, text, f"{path}: {phrase}")
        self.assertIn("Luna at Extra High", (ROOT / "AGENTS.md").read_text())

    def test_expired_anthropic_subscription_is_not_routable(self):
        providers = {cfg.get("provider") for cfg in self.m["executors"].values()}
        self.assertNotIn("anthropic", providers)

    def test_gemini_is_exclusive_to_agy(self):
        gemini = {
            name: cfg for name, cfg in self.m["executors"].items()
            if "gemini" in name or "gemini" in cfg.get("model_id", "").lower()
        }
        self.assertEqual(set(gemini), {"agy-gemini-pro", "agy-gemini-flash"})
        for name, cfg in gemini.items():
            with self.subTest(executor=name):
                self.assertEqual(cfg["provider"], "agy")
                self.assertTrue(cfg["wrapper"].startswith("agy-"))
                self.assertIn("vision", cfg.get("capabilities", []))

    def test_kilo_is_cli_and_free_only(self):
        kilo = {
            name: cfg for name, cfg in self.m["executors"].items()
            if "kilo" in name or cfg.get("provider") == "kilo-cli"
        }
        self.assertEqual(set(kilo), {"kilo-free-auto"})
        cfg = kilo["kilo-free-auto"]
        self.assertEqual(cfg["provider"], "kilo-cli")
        self.assertEqual(cfg["model_id"], "kilo/kilo-auto/free")

    def test_minimax_backup_uses_gjc(self):
        cfg = self.m["executors"]["minimax-m3"]
        self.assertEqual(cfg["provider"], "gjc")
        self.assertEqual(cfg["model_id"], "minimax-code/minimax-m3")

    def test_kimi_is_exclusive_to_native_cli(self):
        kimi = {
            name: cfg for name, cfg in self.m["executors"].items()
            if "kimi" in name or "kimi" in cfg.get("model_id", "").lower()
        }
        self.assertEqual(set(kimi), {"kimi-k27"})
        cfg = kimi["kimi-k27"]
        self.assertEqual(cfg["provider"], "kimi-cli")
        self.assertEqual(cfg["wrapper"], "kimi-cli.sh")
        self.assertIn("vision", cfg.get("capabilities", []))

    def test_primary_zai_lane_uses_glm_52(self):
        zai = self.m["executors"]["zai-glm"]
        self.assertEqual(zai["model_id"], "glm-5.2")
        self.assertEqual(zai["context_window"], 1_000_000)
        self.assertNotIn("vision", zai.get("capabilities", []))

    def test_glm_variants_are_never_vision_capable(self):
        for name, executor in self.m["executors"].items():
            if "glm" in name or "glm" in executor.get("model_id", "").lower():
                with self.subTest(executor=name):
                    self.assertNotIn("vision", executor.get("capabilities", []))

    def test_worker_baseline_requires_ddg_search_fallback(self):
        baseline = (ROOT / "dispatch_packs" / "_baseline.md").read_text()
        self.assertIn("DuckDuckGo", baseline)
        self.assertIn("`ddg` MCP", baseline)
        self.assertIn("Do not fabricate", baseline)

    def test_minimax_m3_context_matches_current_provider(self):
        minimax = self.m["executors"]["minimax-m3"]
        self.assertEqual(minimax["model_id"], "minimax-code/minimax-m3")
        self.assertGreaterEqual(minimax["context_window"], 512_000)

    def test_nested_permissions_reference_real_executors(self):
        for filename in ("dispatch_matrix.toml", "dispatch_matrix.toml.example"):
            with open(ROOT / filename, "rb") as f:
                matrix = tomllib.load(f)
            executors = set(matrix["executors"])
            for edge in matrix["nested_dispatch"]["permissions"]:
                parent, child = edge.split(".", 1)
                self.assertIn(parent, executors, f"{filename}: {edge}")
                self.assertIn(child, executors, f"{filename}: {edge}")

    def test_example_matches_live_matrix(self):
        live = (ROOT / "dispatch_matrix.toml").read_bytes()
        example = (ROOT / "dispatch_matrix.toml.example").read_bytes()
        self.assertEqual(live, example, "dispatch_matrix.toml and .example must be identical")

if __name__ == "__main__":
    unittest.main()
