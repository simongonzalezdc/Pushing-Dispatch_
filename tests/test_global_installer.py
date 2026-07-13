from pathlib import Path
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


if __name__ == "__main__":
    unittest.main()
