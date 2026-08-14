import unittest
import tomllib
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Providers that authenticate via CLI login or run locally (no API key needed).
CLI_OR_LOCAL = {
    "anthropic", "openai-codex", "agy", "gjc", "grok-cli", "kilo-cli",
    "kimi-cli", "ollama", "lm-studio", "unsloth-openai",
}

class TestMatrixShape(unittest.TestCase):
    def setUp(self):
        with open(ROOT / "dispatch_matrix.toml", "rb") as f:
            self.m = tomllib.load(f)

    def test_auto_route_has_ordered_lists(self):
        ar = self.m["auto_route"]
        for key in ("trivial_candidates", "standard_candidates",
                    "local_general_candidates", "local_review_candidates",
                    "local_coding_candidates",
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

    def test_openai_executors_use_current_single_account(self):
        for name, cfg in self.m["executors"].items():
            if cfg.get("provider") == "openai-codex":
                self.assertNotIn("account", cfg, name)

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

    def test_grok_replaces_opus_level_routing(self):
        ar = self.m["auto_route"]
        for key in ("hard_task_candidates", "hard_breakout_candidates", "consult_candidates"):
            with self.subTest(key=key):
                self.assertEqual(ar[key][0], "grok-build")

        # Reversible volume work consumes local/prepaid capacity first; Grok's
        # first-position preference remains scoped to hard and consult lanes.
        self.assertEqual(ar["trivial_candidates"][0], "ollama-xps-gpu")
        self.assertEqual(ar["standard_candidates"][0], "zai-glm")
        self.assertEqual(ar["long_context_candidates"][0], "kimi-k3-cli")

    def test_dell_lane_is_always_gated_by_exact_nuc_validation(self):
        dell = self.m["executors"]["ollama-xps-gpu"]
        self.assertEqual(dell["wrapper"], "cascade-local.sh")
        self.assertEqual(dell["model_id"], "qwen35-2b-max")
        self.assertTrue(dell["health_url"].endswith("/v1/models"))
        self.assertEqual(
            dell["validator_model_id"],
            "unsloth/Qwen3.6-27B-MTP-GGUF",
        )
        self.assertTrue(dell["validator_health_url"].endswith("/v1/models"))
        self.assertIn("Correct only the typo", dell["probe_task"])

    def test_nonresident_qwen35_alias_is_not_routable(self):
        self.assertTrue(self.m["executors"]["lm-studio"]["disabled"])
        for key, candidates in self.m["auto_route"].items():
            if key.endswith("_candidates"):
                self.assertNotIn("lm-studio", candidates, key)

    def test_nuc_context_window_matches_effective_parallel_slot(self):
        # Ornith sticky workhorse on :8890 (32k agent context).
        self.assertEqual(
            self.m["executors"]["unsloth-nucbox"]["context_window"],
            32_768,
        )
        self.assertEqual(
            self.m["executors"]["unsloth-nucbox"]["model_id"],
            "SC117/Ornith-1.0-35B-MTP-APEX-GGUF",
        )

    def test_unsloth_uses_bounded_agentic_pi_harness(self):
        wrapper = (ROOT / "bin" / "wrappers" / "unsloth-nucbox.sh").read_text()
        wrapper_lib = (ROOT / "bin" / "wrappers" / "_exec.sh").read_text()
        executor = self.m["executors"]["unsloth-nucbox"]

        self.assertIn("ce_run_pi_local", wrapper)
        self.assertNotIn("ce_run_openai_compatible", wrapper)
        self.assertEqual(executor["harness_command"], "pi")
        self.assertIn("PI_LOCAL_TIMEOUT_SECONDS", wrapper_lib)
        self.assertIn("--no-context-files", wrapper_lib)
        self.assertTrue(
            (ROOT / "ops" / "unsloth-nucbox" / "pi-agent" / "models.json").is_file()
        )

        result = subprocess.run(
            [
                str(ROOT / "bin" / "wrappers" / "unsloth-nucbox.sh"),
                "--worker-id", "test-unsloth-pi",
                "--cwd", "/tmp",
                "--mode", "task",
                "--task", "Return Status: DONE",
                "--dry-run",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Would execute Pi local model", result.stdout)

    def test_on_demand_qwen_workcells_remain_configured_behind_ornith(self):
        """On-demand :8892 workcells stay defined, but Ornith leads coding/general."""
        expected = {
            "qwen35-35b-general": ("Qwen3.5-35B-A3B-Q4_K_M.gguf", "qwen35-35b-general"),
            "qwen35-27b-review": ("Qwen3.5-27B-Q4_K_M.gguf", "qwen35-27b-review"),
            "qwen36-35b-coding": ("qwen3.6:35b", "qwen36-35b-coding"),
        }
        for executor, (model, profile) in expected.items():
            with self.subTest(executor=executor):
                cfg = self.m["executors"][executor]
                self.assertTrue(cfg["on_demand"])
                self.assertEqual(cfg["model_id"], model)
                self.assertEqual(cfg["workcell_profile"], profile)

        # Sticky Ornith leads the primary local coding + general tiers.
        self.assertEqual(self.m["auto_route"]["local_coding_candidates"][0], "unsloth-nucbox")
        self.assertEqual(self.m["auto_route"]["local_general_candidates"][0], "unsloth-nucbox")
        # Review still prefers the specialist on-demand cell when available.
        self.assertEqual(self.m["auto_route"]["local_review_candidates"][0], "qwen35-27b-review")

        self.assertEqual(
            self.m["executors"]["qwen36-35b-coding"]["context_window"],
            32_768,
        )
        self.assertEqual(
            self.m["executors"]["qwen35-27b-review"]["context_window"],
            32_768,
        )

    def test_local_specialist_tiers_leave_context_headroom(self):
        ar = self.m["auto_route"]
        self.assertLessEqual(ar["local_general_max_tokens"], 24_000)
        self.assertLessEqual(ar["local_review_max_tokens"], 6_000)
        # Ornith coding ceiling: 16k of 32k slot leaves headroom for system+skills+output.
        self.assertLessEqual(ar["local_coding_max_tokens"], 16_000)
        self.assertGreaterEqual(ar["local_coding_max_tokens"], 5_000)

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

    def test_codex_dispatch_allows_projectless_working_directory(self):
        wrapper = ROOT / "bin" / "wrappers" / "codex-luna.sh"
        result = subprocess.run(
            [
                str(wrapper), "--worker-id", "test-projectless",
                "--cwd", "/tmp", "--mode", "task",
                "--task", "Return Status: DONE", "--dry-run",
            ],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--skip-git-repo-check", result.stdout)

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

    def test_current_operator_docs_cover_grok(self):
        paths = (
            ROOT / "AGENTS.md",
            ROOT / "GLOBAL_AGENT_ROUTING.md",
            ROOT / "README.md",
            ROOT / "SETUP_WITH_CLAUDE.md",
            ROOT / "CLAUDE.md",
            ROOT / "INSTALL.md",
            ROOT / "dispatch_packs" / "dispatch-protocol.md",
            ROOT / "dispatch_packs" / "orchestrator-protocol.md",
            ROOT / "docs" / "ORCHESTRATING.md",
            ROOT / "docs" / "PROVIDERS.md",
            ROOT / "docs" / "TROUBLESHOOTING.md",
            ROOT / "docs" / "HERMES.md",
            ROOT / "integrations" / "hermes" / "SKILL.md",
        )
        for path in paths:
            with self.subTest(path=path):
                self.assertIn("grok-build", path.read_text().lower())

        prereqs = (ROOT / "bin" / "check-prereqs.sh").read_text()
        self.assertIn('check_optional "Official Grok CLI" "grok"', prereqs)

        providers = (ROOT / "docs" / "PROVIDERS.md").read_text()
        self.assertIn("Claude Opus-class", providers)
        self.assertIn("plain `grok`", providers)
        self.assertIn('npm install -g @xai-official/grok', providers)
        self.assertIn("grok-4.5", providers)

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

    def test_kimi_k3_routes_keep_cli_and_ollama_credentials_isolated(self):
        kimi = {
            name: cfg for name, cfg in self.m["executors"].items()
            if "kimi" in name or "kimi" in cfg.get("model_id", "").lower()
        }
        self.assertEqual(set(kimi), {"kimi-k3-cli", "kimi-k3-ollama"})
        cli = kimi["kimi-k3-cli"]
        self.assertEqual(cli["provider"], "kimi-cli")
        self.assertEqual(cli["wrapper"], "kimi-k3-cli.sh")
        self.assertEqual(cli["model_id"], "kimi-code/k3")
        self.assertNotIn("key_env", cli)
        ollama = kimi["kimi-k3-ollama"]
        self.assertEqual(ollama["provider"], "ollama-cloud")
        self.assertEqual(ollama["wrapper"], "kimi-k3-ollama-cloud.sh")
        self.assertEqual(ollama["model_id"], "kimi-k3")
        self.assertEqual(ollama["key_env"], "OLLAMA_API_KEY")
        for cfg in (cli, ollama):
            self.assertEqual(cfg["context_window"], 1_048_576)
            self.assertIn("vision", cfg.get("capabilities", []))

    def test_grok_uses_official_native_cli(self):
        grok = self.m["executors"]["grok-build"]
        self.assertEqual(grok["provider"], "grok-cli")
        self.assertEqual(grok["wrapper"], "grok-cli.sh")
        self.assertEqual(grok["model_id"], "grok-4.5")
        self.assertEqual(grok["context_window"], 500_000)
        self.assertIn("vision", grok.get("capabilities", []))

        wrapper = ROOT / "bin" / "wrappers" / "grok-cli.sh"
        result = subprocess.run(
            [
                str(wrapper), "--worker-id", "test-grok",
                "--cwd", "/tmp", "--mode", "task",
                "--task", "Return Status: DONE", "--dry-run",
            ],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Grok model: grok-4.5", result.stdout)

        wrapper_lib = (ROOT / "bin" / "wrappers" / "_exec.sh").read_text()
        self.assertIn('--prompt-file "$prompt_file"', wrapper_lib)
        self.assertIn('--sandbox workspace', wrapper_lib)
        self.assertIn('--sandbox read-only', wrapper_lib)

    def test_primary_zai_lane_uses_glm_52(self):
        zai = self.m["executors"]["zai-glm"]
        self.assertEqual(zai["model_id"], "glm-5.3")
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
