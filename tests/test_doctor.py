import tempfile
import unittest
from unittest import mock
from pathlib import Path
from dispatch_lib import availability, lane_health

class TestDoctorData(unittest.TestCase):
    def test_default_probe_sweep_excludes_on_demand_lanes(self):
        from cli import _automatic_probe_targets

        executors = {
            "resident": {"provider": "ollama"},
            "on-demand": {"provider": "unsloth-openai", "on_demand": True},
            "codex": {"provider": "openai-codex"},
        }
        rows = [
            {"executor": name, "available": True}
            for name in executors
        ]
        self.assertEqual(_automatic_probe_targets(rows, executors), ["resident"])

    def test_probe_uses_matrix_declared_task(self):
        from cli import _probe_executor

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            wrappers = root / "bin" / "wrappers"
            wrappers.mkdir(parents=True)
            wrapper = wrappers / "probe.sh"
            wrapper.write_text(
                "#!/bin/sh\n"
                "[ \"$1\" = \"--task\" ] && [ \"$2\" = \"custom probe\" ]\n",
                encoding="utf-8",
            )
            wrapper.chmod(0o755)
            result = _probe_executor(
                "local",
                {
                    "wrapper": "probe.sh",
                    "allowed_modes": ["task"],
                    "probe_task": "custom probe",
                },
                str(root),
            )

        self.assertEqual(result["probe"], "OK")

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
