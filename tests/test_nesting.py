import unittest
import tomllib
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent

class TestNesting(unittest.TestCase):
    def test_max_depth_is_two(self):
        with open(ROOT / "dispatch_matrix.toml", "rb") as f:
            m = tomllib.load(f)
        self.assertEqual(m["nested_dispatch"]["max_depth"], 2)

if __name__ == "__main__":
    unittest.main()
