import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class GlobalInstallerTests(unittest.TestCase):
    def test_launcher_selects_supported_python(self) -> None:
        installer = (ROOT / "bin" / "install-global-routing.sh").read_text()

        self.assertIn("sys.version_info < (3, 10)", installer)
        self.assertIn("/opt/homebrew/bin/python3", installer)
        self.assertIn("/usr/local/bin/python3", installer)
        self.assertIn("DISPATCH_PYTHON", installer)
        self.assertIn("requires Python 3.10 or newer", installer)

    def test_launcher_uses_shared_hermes_zai_reader(self) -> None:
        installer = (ROOT / "bin" / "install-global-routing.sh").read_text()

        self.assertIn("read-hermes-zai-key", installer)
        self.assertIn("Z_AI_API_KEY", installer)
        self.assertNotIn('source "$HOME/.hermes/.env"', installer)

    def test_generated_launcher_imports_hermes_zai_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            hermes = home / ".hermes"
            hermes.mkdir()
            env_file = hermes / ".env"
            env_file.write_text("Z_AI_API_KEY=from-hermes\n")
            env_file.chmod(0o600)
            fake_python = home / "python3"
            fake_python.write_text(
                "#!/usr/bin/env bash\n"
                "[[ ${1:-} == -c ]] && exit 0\n"
                "printf '%s' \"${Z_AI_API_KEY:-missing}\"\n"
            )
            fake_python.chmod(0o700)

            subprocess.run(
                ["bash", ROOT / "bin" / "install-global-routing.sh"],
                env={**os.environ, "HOME": str(home)},
                check=True,
                text=True,
                capture_output=True,
            )
            result = subprocess.run(
                [home / ".local" / "bin" / "pushing-dispatch", "doctor"],
                env={**os.environ, "HOME": str(home), "DISPATCH_PYTHON": str(fake_python)},
                text=True,
                capture_output=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "from-hermes")


if __name__ == "__main__":
    unittest.main()
