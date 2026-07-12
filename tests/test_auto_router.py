import unittest
from unittest import mock
from dispatch_lib import auto_router

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
    def test_explicit_executor_passthrough(self):
        self.assertEqual(
            auto_router.auto_route("x", "task", matrix_dict=MATRIX, explicit_executor="opus"),
            "opus")

    def test_trivial_picks_first_available(self):
        self.assertEqual(route("fix typo", "task", available=["openai-mini", "zai-glm"]), "openai-mini")

    def test_trivial_falls_back_when_first_unavailable(self):
        self.assertEqual(route("fix typo", "task", available=["zai-glm"]), "zai-glm")

    def test_hard_task_leads_with_strong_model(self):
        t = "implement and debug complex concurrency logic"
        self.assertEqual(route(t, "task", available=["codex-spark", "opus"]), "codex-spark")

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

if __name__ == "__main__":
    unittest.main()
