import tomllib
import unittest
from unittest import mock
from pathlib import Path

from dispatch_lib import availability


ROOT = Path(__file__).resolve().parent.parent


class TestCloudEntitlementQuarantine(unittest.TestCase):
    def test_grok_is_disabled_in_live_and_example_matrices(self):
        for filename in ("dispatch_matrix.toml", "dispatch_matrix.toml.example"):
            with self.subTest(filename=filename):
                with open(ROOT / filename, "rb") as handle:
                    matrix = tomllib.load(handle)
                self.assertTrue(matrix["executors"]["grok-build"]["disabled"])

    def test_disabled_lane_cannot_survive_true_availability_cache(self):
        matrix = {"executors": {"cloud": {"provider": "cloud-cli", "disabled": True}}}
        cached = {"cloud": {"provider": "cloud-cli", "available": True}}
        with mock.patch.object(availability, "_read_cache", return_value=cached), mock.patch(
            "dispatch_lib.lane_health.prune"
        ):
            resolved = availability.resolve(matrix, use_cache=True)
        self.assertFalse(resolved["cloud"]["available"])


if __name__ == "__main__":
    unittest.main()
