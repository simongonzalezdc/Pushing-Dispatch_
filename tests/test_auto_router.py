import unittest
import tomllib
from unittest import mock
from pathlib import Path
from dispatch_lib import auto_router

ROOT = Path(__file__).resolve().parent.parent

MATRIX = {
    "executors": {
        "openai-mini":       {"provider": "openai-codex", "allowed_modes": ["task", "consult"], "capabilities": ["vision"]},
        "codex-spark":       {"provider": "openai-codex", "allowed_modes": ["task", "breakout"], "capabilities": ["vision"]},
        "openai-gpt55-high": {"provider": "openai-codex", "allowed_modes": ["task", "breakout", "consult"], "capabilities": ["vision"]},
        "zai-glm":           {"provider": "zai", "allowed_modes": ["task", "breakout", "consult"], "capabilities": []},
        "opus":              {"provider": "anthropic", "allowed_modes": ["task", "breakout", "consult"], "capabilities": ["vision"]},
        "kimi-coding":       {"provider": "kimi", "allowed_modes": ["task", "consult"], "capabilities": ["vision"]},
    },
    "auto_route": {
        "trivial_candidates": ["openai-mini", "zai-glm"],
        "hard_task_candidates": ["codex-spark", "openai-gpt55-high", "zai-glm", "opus"],
        "long_context_candidates": ["kimi-coding", "opus"],
        "consult_candidates": ["opus", "openai-gpt55-high"],
        "standard_candidates": ["codex-spark", "zai-glm"],
        "hard_breakout_candidates": ["openai-gpt55-high", "opus"],
        "trivial_threshold_tokens": 5000,
        "long_context_threshold_tokens": 50000,
    },
}

def route(task, mode, available, cooldown=()):
    with mock.patch.object(auto_router, "available_set", return_value=set(available)), \
         mock.patch.object(auto_router, "in_cooldown", side_effect=lambda e: e in cooldown):
        return auto_router.auto_route(task, mode, matrix_dict=MATRIX)

class TestRouter(unittest.TestCase):
    def test_explicit_available_executor_is_allowed(self):
        with mock.patch.object(auto_router, "available_set", return_value={"opus"}), \
             mock.patch.object(auto_router, "in_cooldown", return_value=False):
            self.assertEqual(
                auto_router.auto_route("x", "task", matrix_dict=MATRIX, explicit_executor="opus"),
                "opus")

    def test_explicit_unavailable_executor_fails_closed(self):
        with mock.patch.object(auto_router, "available_set", return_value=set()), \
             mock.patch.object(auto_router, "in_cooldown", return_value=False):
            with self.assertRaisesRegex(auto_router.NoExecutorAvailable, "Explicit executor 'opus' is unavailable"):
                auto_router.auto_route("x", "task", matrix_dict=MATRIX, explicit_executor="opus")

    def test_trivial_picks_first_available(self):
        self.assertEqual(route("fix typo", "task", available=["openai-mini", "zai-glm"]), "openai-mini")

    def test_natural_language_typo_is_trivial(self):
        self.assertEqual(route("fix a typo", "task", available=["openai-mini", "zai-glm"]), "openai-mini")

    def test_short_nonmechanical_task_uses_standard_tier(self):
        self.assertEqual(
            route("write the account recovery flow", "task", available=["codex-spark", "openai-mini"]),
            "codex-spark",
        )

    def test_plain_implementation_is_standard_not_hard(self):
        self.assertEqual(
            route("implement the account recovery flow", "task", available=["codex-spark", "openai-gpt55-high"]),
            "codex-spark",
        )

    def test_trivial_falls_back_when_first_unavailable(self):
        self.assertEqual(route("fix typo", "task", available=["zai-glm"]), "zai-glm")

    def test_hard_task_leads_with_strong_model(self):
        t = "implement and debug complex concurrency logic"
        self.assertEqual(route(t, "task", available=["codex-spark", "opus"]), "codex-spark")

    def test_adversarial_review_routes_to_grok_in_live_matrix(self):
        with open(ROOT / "dispatch_matrix.toml", "rb") as f:
            matrix = tomllib.load(f)
        with mock.patch.object(auto_router, "available_set", return_value={"grok-build", "codex-luna"}), \
             mock.patch.object(auto_router, "in_cooldown", return_value=False):
            executor, tier = auto_router.auto_route(
                "Perform an adversarial review of this security-sensitive patch",
                "task",
                matrix_dict=matrix,
                return_tier=True,
            )
        self.assertEqual(tier, "hard_task_candidates")
        self.assertEqual(executor, "grok-build")

    def test_cooldown_skips_executor(self):
        t = "implement and debug complex concurrency logic"
        self.assertEqual(
            route(t, "task", available=["codex-spark", "openai-gpt55-high", "opus"],
                  cooldown=["codex-spark"]),
            "openai-gpt55-high")

    def test_long_context_keyword(self):
        self.assertEqual(route("summarize the entire codebase", "task",
                               available=["kimi-coding", "opus"]), "kimi-coding")

    def test_explicit_vision_required_skips_visionless_executor(self):
        self.assertEqual(
            route("VISION REQUIRED: inspect the supplied UI", "task",
                  available=["zai-glm", "opus"]),
            "opus")

    def test_visual_inspection_terms_skip_visionless_executor(self):
        for task in (
            "inspect this screenshot for layout defects",
            "review the attached image",
            "perform a render inspection before approving",
        ):
            with self.subTest(task=task):
                self.assertEqual(route(task, "task", available=["zai-glm", "opus"]), "opus")

    def test_vision_requirement_explains_capability_rejection_when_none_eligible(self):
        with self.assertRaisesRegex(
            auto_router.NoExecutorAvailable,
            r"requires vision; rejected: zai-glm \(missing vision capability\)",
        ):
            route("VISION REQUIRED: inspect the supplied UI", "task", available=["zai-glm"])

    def test_nonvisual_routing_is_unchanged_by_capability_metadata(self):
        self.assertEqual(route("fix typo", "task", available=["openai-mini", "zai-glm"]), "openai-mini")

    def test_errors_when_nothing_available(self):
        with self.assertRaises(auto_router.NoExecutorAvailable):
            route("fix typo", "task", available=[])

    def test_live_matrix_routes_only_atomic_mechanical_work_to_dell(self):
        with open(ROOT / "dispatch_matrix.toml", "rb") as f:
            matrix = tomllib.load(f)
        available = set(matrix["executors"])
        with mock.patch.object(auto_router, "available_set", return_value=available), \
             mock.patch.object(auto_router, "in_cooldown", return_value=False):
            atomic_executor, atomic_tier = auto_router.auto_route(
                "Correct the typo in this exact sentence.",
                "task",
                matrix_dict=matrix,
                return_tier=True,
            )
            broad_executor, broad_tier = auto_router.auto_route(
                "Refactor an authentication subsystem across twelve files and design the migration.",
                "task",
                matrix_dict=matrix,
                return_tier=True,
            )
        self.assertEqual((atomic_executor, atomic_tier), ("ollama-xps-gpu", "trivial_candidates"))
        self.assertNotEqual(broad_executor, "ollama-xps-gpu")
        self.assertEqual(broad_tier, "hard_task_candidates")

    def test_repository_wide_mechanical_phrases_never_route_to_dell(self):
        with open(ROOT / "dispatch_matrix.toml", "rb") as f:
            matrix = tomllib.load(f)
        available = set(matrix["executors"])
        tasks = (
            "Lint all files in the repository.",
            "Rename this API across the repo.",
            "Refactor the entire codebase.",
            "Format every file.",
        )
        with mock.patch.object(auto_router, "available_set", return_value=available), \
             mock.patch.object(auto_router, "in_cooldown", return_value=False):
            for task in tasks:
                with self.subTest(task=task):
                    executor, tier = auto_router.auto_route(
                        task,
                        "task",
                        matrix_dict=matrix,
                        return_tier=True,
                    )
                    self.assertNotEqual(executor, "ollama-xps-gpu")
                    self.assertEqual(tier, "hard_task_candidates")

            executor, _tier = auto_router.auto_route(
                "Fix typos in README and docs.",
                "task",
                matrix_dict=matrix,
                return_tier=True,
            )
            self.assertNotEqual(executor, "ollama-xps-gpu")

    def test_live_matrix_routes_bounded_general_work_to_ornith(self):
        with open(ROOT / "dispatch_matrix.toml", "rb") as f:
            matrix = tomllib.load(f)
        with mock.patch.object(auto_router, "available_set", return_value=set(matrix["executors"])), \
             mock.patch.object(auto_router, "in_cooldown", return_value=False):
            executor, tier = auto_router.auto_route(
                "Summarize these four short paragraphs into five factual bullets.",
                "task",
                matrix_dict=matrix,
                return_tier=True,
            )
        self.assertEqual((executor, tier), ("unsloth-nucbox", "local_general_candidates"))

    def test_live_matrix_routes_bounded_review_to_qwen35_27b(self):
        with open(ROOT / "dispatch_matrix.toml", "rb") as f:
            matrix = tomllib.load(f)
        with mock.patch.object(auto_router, "available_set", return_value=set(matrix["executors"])), \
             mock.patch.object(auto_router, "in_cooldown", return_value=False):
            executor, tier = auto_router.auto_route(
                "Review this one configuration file for contradictions and report only grounded findings.",
                "task",
                matrix_dict=matrix,
                return_tier=True,
            )
        self.assertEqual((executor, tier), ("qwen35-27b-review", "local_review_candidates"))

    def test_live_matrix_routes_bounded_coding_to_ornith(self):
        with open(ROOT / "dispatch_matrix.toml", "rb") as f:
            matrix = tomllib.load(f)
        with mock.patch.object(auto_router, "available_set", return_value=set(matrix["executors"])), \
             mock.patch.object(auto_router, "in_cooldown", return_value=False):
            executor, tier = auto_router.auto_route(
                "Implement a bounded one-file Python validator using the existing tests.",
                "task",
                matrix_dict=matrix,
                return_tier=True,
            )
        self.assertEqual((executor, tier), ("unsloth-nucbox", "local_coding_candidates"))

    def test_local_specialist_context_ceiling_falls_back_to_standard_tier(self):
        with open(ROOT / "dispatch_matrix.toml", "rb") as f:
            matrix = tomllib.load(f)
        oversized_review = "Review this one file for contradictions. " + ("evidence " * 7000)
        with mock.patch.object(auto_router, "available_set", return_value=set(matrix["executors"])), \
             mock.patch.object(auto_router, "in_cooldown", return_value=False):
            executor, tier = auto_router.auto_route(
                oversized_review,
                "task",
                matrix_dict=matrix,
                return_tier=True,
            )
        self.assertEqual(tier, "standard_candidates")
        self.assertEqual(executor, "zai-glm")

if __name__ == "__main__":
    unittest.main()
