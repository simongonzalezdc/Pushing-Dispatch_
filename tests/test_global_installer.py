import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class GlobalInstallerTests(unittest.TestCase):
    def test_generated_launcher_resolves_environment_at_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            clean = {"HOME": str(home), "PATH": os.defpath}
            fake_python = home / "fake-python"
            fake_python.write_text(
                "#!/usr/bin/env bash\n"
                "[[ ${1:-} == -c ]] && exit 0\n"
                "printf '%s\\n' \"$DISPATCH_MATRIX\" \"$DISPATCH_NESTED\"\n"
            )
            fake_python.chmod(0o700)
            for install_overrides in ({}, {
                "REPO": "/wrong-install-repo",
                "DISPATCH_MATRIX": "/wrong-install-matrix",
                "DISPATCH_NESTED": "wrong-install-value",
            }):
                with self.subTest(install_overrides=install_overrides):
                    subprocess.run(
                        ["bash", ROOT / "bin" / "install-global-routing.sh"],
                        env={**clean, **install_overrides},
                        check=True, capture_output=True, text=True, timeout=10,
                    )
                    for overrides, expected in (
                        ({}, [str(ROOT / "dispatch_matrix.toml"), "1"]),
                        ({"DISPATCH_MATRIX": "/runtime path/matrix.toml",
                          "DISPATCH_NESTED": "0"},
                         ["/runtime path/matrix.toml", "0"]),
                    ):
                        result = subprocess.run(
                            [home / ".local/bin/pushing-dispatch", "doctor"],
                            env={**clean, "DISPATCH_PYTHON": str(fake_python),
                                 **overrides},
                            check=True, capture_output=True, text=True, timeout=10,
                        )
                        self.assertEqual(result.stdout.splitlines(), expected)

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
