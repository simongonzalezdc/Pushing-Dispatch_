import os
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FactoryCapabilityFlagTests(unittest.TestCase):
    def _dry_run(self, **factory_env: str) -> str:
        script = r'''
source bin/wrappers/_exec.sh
ce_run_claude --cwd "$PWD" --task "bounded Factory role" --worker-id w-factory-test --dry-run
'''
        result = subprocess.run(
            ["bash", "-c", script],
            cwd=ROOT,
            env={**os.environ, "CE_BARE_MODE": "1", **factory_env},
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def test_factory_manifest_restricts_actual_claude_surface(self):
        output = self._dry_run(
            FACTORY_ALLOWED_TOOLS="Bash,Edit,Read",
            FACTORY_DISABLE_SKILLS="1",
            FACTORY_STRICT_MCP="1",
        )

        self.assertIn("--tools Bash,Edit,Read", output)
        self.assertIn("--allowed-tools Bash,Edit,Read", output)
        self.assertIn("--disable-slash-commands", output)
        self.assertIn("--strict-mcp-config", output)
        self.assertIn("--no-chrome", output)

    def test_non_factory_dispatch_surface_is_unchanged(self):
        output = self._dry_run()

        self.assertNotIn("--tools ", output)
        self.assertNotIn("--allowed-tools", output)
        self.assertNotIn("--disable-slash-commands", output)
        self.assertNotIn("--strict-mcp-config", output)
        self.assertNotIn("--no-chrome", output)


if __name__ == "__main__":
    unittest.main()
