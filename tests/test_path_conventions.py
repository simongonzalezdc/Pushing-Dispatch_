import unittest
from dispatch_lib import path_conventions as pc

class TestPaths(unittest.TestCase):
    def test_new_state_paths_under_dispatch_root(self):
        root = pc.dispatch_root()
        self.assertEqual(pc.availability_path(), root / "availability.json")
        self.assertEqual(pc.lane_health_path(), root / "lane_health.json")
        self.assertEqual(pc.outcomes_path(), root / "outcomes.jsonl")

if __name__ == "__main__":
    unittest.main()
