import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

from dispatch_lib.current_worker_index import Limits, build_index, main, publish_index


class CurrentWorkerIndexTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.status = self.root / "status"
        self.status.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, worker_id, phase="reading", **extra):
        value = {"worker_id": worker_id, "current_phase": phase, **extra}
        (self.status / f"{worker_id}.json").write_text(json.dumps(value))

    def test_large_history_finds_active_tail_and_separates_checkpoint_unknown(self):
        for index in range(4448):
            self.write(f"w-old-{index}", "done")
        self.write("w-live", "writing")
        self.write("w-check", "awaiting_checkpoint")
        self.write("w-unknown", "future_phase")
        result = build_index(self.status, monotonic=lambda: 0.0)
        self.assertEqual(
            set(result["candidate_worker_ids"]), {"w-live", "w-check", "w-unknown"}
        )
        self.assertEqual(result["awaiting_checkpoint_worker_ids"], ["w-check"])
        self.assertEqual(result["counts"]["phase_unknown"], 1)

    def test_publish_limit_is_explicit_and_counts_are_exact(self):
        for index in range(140):
            self.write(f"w-{index:03}")
        result = build_index(self.status)
        self.assertEqual(len(result["candidate_worker_ids"]), 128)
        self.assertEqual(result["counts"]["omitted"], 12)
        self.assertEqual(result["coverage"]["stop_reason"], "PUBLISH_LIMIT")
        self.assertFalse(result["coverage"]["complete"])

    def test_entry_byte_and_clock_budgets_fail_honestly(self):
        for index in range(4):
            self.write(f"w-{index}")
        entry = build_index(self.status, limits=Limits(entries=1))
        self.assertEqual(entry["coverage"]["stop_reason"], "ENTRY_LIMIT")
        byte = build_index(self.status, limits=Limits(bytes=1))
        self.assertEqual(byte["coverage"]["stop_reason"], "BYTE_LIMIT")
        ticks = iter([0.0, 0.0, 3.0])
        clock = build_index(
            self.status, monotonic=lambda: next(ticks), limits=Limits(seconds=2)
        )
        self.assertEqual(clock["coverage"]["stop_reason"], "TIME_LIMIT")

    def test_symlink_fifo_oversize_and_malformed_are_not_read_as_workers(self):
        self.write("w-target")
        os.symlink(self.status / "w-target.json", self.status / "w-link.json")
        os.mkfifo(self.status / "w-pipe.json")
        (self.status / "w-large.json").write_bytes(b"x" * 65537)
        (self.status / "w-bad.json").write_text("{")
        result = build_index(self.status)
        self.assertEqual(result["candidate_worker_ids"], ["w-target"])
        self.assertEqual(result["counts"]["malformed"], 4)

    def test_exact_file_read_limit_is_accepted(self):
        # Whitespace makes a valid object exactly the maximum encoded size.
        raw = b'{"worker_id":"w-max","current_phase":"reading"}'
        (self.status / "w-max.json").write_bytes(raw + b" " * (65536 - len(raw)))
        result = build_index(self.status)
        self.assertEqual(result["candidate_worker_ids"], ["w-max"])
        self.assertEqual(result["coverage"]["bytes_read"], 65536)

    def test_raced_generation_retries_once(self):
        first = {"source_generation": {"consistent": False}}
        second = {
            "source_generation": {"consistent": True},
            "generated_at": "x",
            "coverage": {},
            "counts": {},
        }
        with (
            mock.patch(
                "dispatch_lib.current_worker_index.build_index",
                side_effect=[first, second],
            ) as build,
            mock.patch.dict(os.environ, {"DISPATCH_ROOT": str(self.root)}),
        ):
            result = publish_index(root=self.status)
        self.assertIs(result, second)
        self.assertEqual(build.call_count, 2)

    def test_atomic_status_replacement_marks_generation_inconsistent(self):
        self.write("w-race", "reading")
        calls = 0

        def replace_during_scan():
            nonlocal calls
            calls += 1
            if calls == 2:
                replacement = self.status / ".replacement"
                replacement.write_text(
                    json.dumps({"worker_id": "w-race", "current_phase": "writing"})
                )
                os.replace(replacement, self.status / "w-race.json")
            return 0.0

        result = build_index(self.status, monotonic=replace_during_scan)
        self.assertFalse(result["source_generation"]["consistent"])
        self.assertFalse(result["coverage"]["complete"])

    def test_write_or_fsync_failure_preserves_old_index(self):
        target = self.root / "current-workers.json"
        target.write_text("old\n")
        self.write("w-live")
        with (
            mock.patch.dict(os.environ, {"DISPATCH_ROOT": str(self.root)}),
            mock.patch(
                "dispatch_lib.current_worker_index.os.fsync",
                side_effect=OSError("no fsync"),
            ),
        ):
            with self.assertRaises(OSError):
                publish_index(root=self.status)
        self.assertEqual(target.read_text(), "old\n")
        self.assertEqual(list(self.root.glob(".current-workers.json.*")), [])

    def test_directory_fsync_failure_rolls_back_old_index(self):
        target = self.root / "current-workers.json"
        target.write_text("old\n")
        self.write("w-live")
        with (
            mock.patch.dict(os.environ, {"DISPATCH_ROOT": str(self.root)}),
            mock.patch(
                "dispatch_lib.current_worker_index.os.fsync",
                side_effect=[None, OSError("directory fsync failed")],
            ),
        ):
            with self.assertRaises(OSError):
                publish_index(root=self.status)
        self.assertEqual(target.read_text(), "old\n")
        self.assertEqual(list(self.root.glob(".current-workers.json.*")), [])

    def test_close_failure_preserves_old_index(self):
        target = self.root / "current-workers.json"
        target.write_text("old\n")
        self.write("w-live")
        real_fdopen = os.fdopen

        class CloseFailure:
            def __init__(self, handle):
                self.handle = handle

            def __enter__(self):
                return self.handle

            def __exit__(self, *_):
                self.handle.close()
                raise OSError("close failed")

        def failing_fdopen(*args, **kwargs):
            return CloseFailure(real_fdopen(*args, **kwargs))

        with (
            mock.patch.dict(os.environ, {"DISPATCH_ROOT": str(self.root)}),
            mock.patch(
                "dispatch_lib.current_worker_index.os.fdopen",
                side_effect=failing_fdopen,
            ),
        ):
            with self.assertRaises(OSError):
                publish_index(root=self.status)
        self.assertEqual(target.read_text(), "old\n")
        self.assertEqual(list(self.root.glob(".current-workers.json.*")), [])

    def test_fixed_output_rejects_arbitrary_path(self):
        with mock.patch.dict(os.environ, {"DISPATCH_ROOT": str(self.root)}):
            with self.assertRaises(ValueError):
                publish_index(root=self.status, output=self.root / "elsewhere.json")

    def test_module_entrypoint_has_no_output_path_argument(self):
        self.write("w-live")
        with (
            mock.patch.dict(os.environ, {"DISPATCH_ROOT": str(self.root)}),
            redirect_stdout(StringIO()),
        ):
            self.assertEqual(main([]), 0)
        self.assertTrue((self.root / "current-workers.json").is_file())
        with (
            self.assertRaises(SystemExit),
            redirect_stdout(StringIO()),
            redirect_stderr(StringIO()),
        ):
            main(["--output", "/tmp/escape"])


if __name__ == "__main__":
    unittest.main()
