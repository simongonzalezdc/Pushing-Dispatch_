import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]


class HermesCredentialReaderTests(unittest.TestCase):
    def test_reads_only_allowlisted_key_without_executing_dotenv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            hermes = home / ".hermes"
            hermes.mkdir()
            sentinel = home / "executed"
            env_file = hermes / ".env"
            env_file.write_text(
                f"UNRELATED=$(touch {sentinel})\n"
                "ANTHROPIC_API_KEY=forbidden\n"
                "GLM_API_KEY='glm=value#safe'\n"
                "Z_AI_API_KEY=preferred\n"
            )
            env_file.chmod(0o600)

            result = subprocess.run(
                [ROOT / "bin" / "read-hermes-zai-key"],
                env={**os.environ, "HOME": str(home)},
                text=True,
                capture_output=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "preferred")
            self.assertFalse(sentinel.exists())

    def test_rejects_group_readable_dotenv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            hermes = home / ".hermes"
            hermes.mkdir()
            env_file = hermes / ".env"
            env_file.write_text("Z_AI_API_KEY=unsafe\n")
            env_file.chmod(0o640)

            result = subprocess.run(
                [ROOT / "bin" / "read-hermes-zai-key"],
                env={**os.environ, "HOME": str(home)},
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")


class HermesDispatchAdapterTests(unittest.TestCase):
    def test_start_routes_external_worker_through_dispatch_auto(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "args"
            fake = Path(tmp) / "pushing-dispatch"
            fake.write_text("#!/usr/bin/env bash\nprintf '%s\\n' \"$@\" > \"$HERMES_DISPATCH_TEST_LOG\"\n")
            fake.chmod(0o700)

            result = subprocess.run(
                [ROOT / "bin" / "hermes-dispatch", "start", "--mode", "task", "--task", "fix it", "--cwd", tmp],
                env={
                    **os.environ,
                    "PUSHING_DISPATCH_BIN": str(fake),
                    "HERMES_DISPATCH_TEST_LOG": str(log),
                },
                text=True,
                capture_output=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                log.read_text().splitlines(),
                ["task", "start", "--executor", "auto", "--task", "fix it", "--cwd", tmp],
            )

    def test_status_is_forwarded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "args"
            fake = Path(tmp) / "pushing-dispatch"
            fake.write_text("#!/usr/bin/env bash\nprintf '%s\\n' \"$@\" > \"$HERMES_DISPATCH_TEST_LOG\"\n")
            fake.chmod(0o700)

            result = subprocess.run(
                [ROOT / "bin" / "hermes-dispatch", "status", "worker-1"],
                env={
                    **os.environ,
                    "PUSHING_DISPATCH_BIN": str(fake),
                    "HERMES_DISPATCH_TEST_LOG": str(log),
                },
                text=True,
                capture_output=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(log.read_text().splitlines(), ["status", "worker-1"])

    def test_start_rejects_executor_override(self) -> None:
        result = subprocess.run(
            [ROOT / "bin" / "hermes-dispatch", "start", "--executor", "codex-sol", "--task", "bypass"],
            env={**os.environ, "PUSHING_DISPATCH_BIN": "/usr/bin/true"},
            text=True,
            capture_output=True,
        )

        self.assertEqual(result.returncode, 64)
        self.assertIn("executor selection belongs to Pushing Dispatch", result.stderr)


class HermesConfigTests(unittest.TestCase):
    def test_configurator_prunes_retired_native_providers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config.yaml"
            config.write_text(
                yaml.safe_dump(
                    {
                        "model": {"provider": "nous", "default": "openai/gpt-5.5"},
                        "providers": {"nous": {}, "zai": {"model": "glm-5.3"}},
                        "fallback_providers": [{"provider": "zai", "model": "glm-4.6"}],
                        "custom_providers": [{"name": "nucbox-gemma4"}],
                        "delegation": {"provider": "zai", "model": "glm-5.3", "max_iterations": 48},
                        "unrelated": {"preserved": True},
                    }
                )
            )

            result = subprocess.run(
                ["python3", ROOT / "bin" / "configure-hermes-routing.py", "--config", config],
                text=True,
                capture_output=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            updated = yaml.safe_load(config.read_text())
            self.assertEqual(updated["model"]["provider"], "zai")
            self.assertEqual(updated["model"]["default"], "glm-5.3")
            self.assertEqual(set(updated["providers"]), {"zai", "ollama-local"})
            self.assertEqual(updated["providers"]["zai"]["model"], "glm-5.3")
            self.assertEqual(updated["fallback_providers"], [])
            self.assertEqual(updated["custom_providers"], [])
            self.assertEqual(updated["delegation"]["model"], "glm-5.3")
            self.assertEqual(updated["delegation"]["max_iterations"], 48)
            self.assertTrue(updated["unrelated"]["preserved"])
            self.assertEqual(config.stat().st_mode & 0o777, 0o600)

    def test_installer_adds_adapter_skill_and_canonical_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            hermes = home / ".hermes"
            hermes.mkdir()
            config = hermes / "config.yaml"
            config.write_text(
                yaml.safe_dump(
                    {
                        "model": {"provider": "nous", "default": "openai/gpt-5.5"},
                        "providers": {"nous": {}},
                        "delegation": {"max_iterations": 12},
                    }
                )
            )

            result = subprocess.run(
                ["bash", ROOT / "bin" / "install-hermes-routing.sh"],
                env={
                    **os.environ,
                    "HOME": str(home),
                    "HERMES_HOME": str(hermes),
                    "HERMES_PYTHON": sys.executable,
                },
                text=True,
                capture_output=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((home / ".local" / "bin" / "hermes-dispatch").is_symlink())
            skill = hermes / "skills" / "pushing-dispatch" / "SKILL.md"
            self.assertIn("hermes-dispatch start", skill.read_text())
            updated = yaml.safe_load(config.read_text())
            self.assertEqual(updated["model"]["default"], "glm-5.3")
            self.assertEqual(updated["delegation"]["max_iterations"], 12)


if __name__ == "__main__":
    unittest.main()
