"""Dry-run wrapper termination: prompt return, zero owned residue.

CS FULL-SUITE-BLOCKER-DIAGNOSIS: the Wave-2 heartbeat loop was created even
for --dry-run, and every dry-run path returns before the terminal
ce_finalize_status that stops it. The orphaned loop held the parent's
stdout/stderr, so a captured-pipe parent blocked on EOF after the wrapper
exited 0 (tests/test_factory_capability_flags.py hang).

These are real subprocess runs in a private dispatch root with a new
process group: they require the dry run to return promptly, the heartbeat
status file to never be created, and the process group to drain completely
(no orphaned loop or sleep child). Bounded cleanup kills the group if a
regression hangs. Normal (non-dry-run) heartbeat behavior is covered by
NormalHeartbeatTests below and must stay intact.
"""
import os
import signal
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Entry points CS verified to reproduce the shared leak; all funnel through
# the common ce_parse_args boundary where the heartbeat lifecycle lives.
DRY_RUN_ENTRYPOINTS = {
    "ce_run_claude": "DRY RUN - Would execute:",
    "ce_run_codex": "DRY RUN - Would execute:",
    # pi_local echoes its provider/model and returns 0 before reading the
    # agent config; the synthetic env only satisfies command construction.
    "ce_run_pi_local": "DRY RUN - Would execute Pi local model:",
}


def _kill_group_bounded(pgid: int, grace: float = 2.0) -> None:
    """Bounded test-failure cleanup: TERM then KILL for a whole group."""
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + grace
    while time.monotonic() < deadline:
        try:
            os.killpg(pgid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.05)
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def _group_drained(pgid: int, timeout: float = 5.0) -> bool:
    """True once no live process remains in the group (bounded wait)."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            os.killpg(pgid, 0)
        except ProcessLookupError:
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.05)


class WrapperDryRunTerminationTests(unittest.TestCase):
    def _run_dry_run(self, entrypoint: str):
        tmp = tempfile.TemporaryDirectory(prefix="wrapper-dryrun-")
        self.addCleanup(tmp.cleanup)
        dispatch_root = Path(tmp.name) / "dispatch"
        worker_id = "w-dryrun-residue-check"
        script = f"""
set -euo pipefail
source bin/wrappers/_exec.sh
{entrypoint} --cwd "$PWD" --task "bounded dry run" --worker-id {worker_id} --dry-run
"""
        env = {
            **os.environ,
            "CE_BARE_MODE": "1",
            "DISPATCH_ROOT": str(dispatch_root),
            "TMPDIR": str(tmp.name),
            # Synthetic Pi config: dry-run only echoes these values and
            # returns before any registry read or endpoint contact.
            "PI_LOCAL_PROVIDER": "synthetic-provider",
            "PI_LOCAL_MODEL": "synthetic-model",
            "PI_LOCAL_AGENT_DIR": str(Path(tmp.name) / "pi-agent"),
        }
        process = subprocess.Popen(
            ["bash", "-c", script],
            cwd=ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        pgid = process.pid
        self.addCleanup(_kill_group_bounded, pgid)
        try:
            stdout, stderr = process.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            _kill_group_bounded(pgid)
            self.fail(f"{entrypoint} --dry-run did not return promptly")
        return process, stdout, stderr, dispatch_root, worker_id, pgid

    def test_dry_run_returns_promptly_with_zero_residue(self):
        for entrypoint, marker in DRY_RUN_ENTRYPOINTS.items():
            with self.subTest(entrypoint=entrypoint):
                process, stdout, stderr, dispatch_root, worker_id, pgid = \
                    self._run_dry_run(entrypoint)
                self.assertEqual(
                    process.returncode, 0,
                    f"{entrypoint}: {stdout}{stderr}")
                if marker is not None:
                    self.assertIn(marker, stdout)
                heartbeat = dispatch_root / "status" / f"{worker_id}.heartbeat"
                self.assertFalse(
                    heartbeat.exists(),
                    "dry run must not create a heartbeat status file")
                self.assertTrue(
                    _group_drained(pgid),
                    "process group must drain: no orphaned heartbeat loop "
                    "or sleep child may survive the dry run")


class NormalHeartbeatTests(unittest.TestCase):
    """The dry-run skip must not weaken the real worker heartbeat."""

    def test_normal_parse_starts_heartbeat_and_stop_is_truthful(self):
        tmp = tempfile.TemporaryDirectory(prefix="wrapper-heartbeat-")
        self.addCleanup(tmp.cleanup)
        dispatch_root = Path(tmp.name) / "dispatch"
        worker_id = "w-heartbeat-normal-check"
        script = f"""
set -euo pipefail
source bin/wrappers/_exec.sh
ce_parse_args --cwd "$PWD" --task "bounded run" --worker-id {worker_id}
for i in 1 2 3 4 5; do
    [[ -f "$DISPATCH_ROOT/status/{worker_id}.heartbeat" ]] && break
    sleep 0.2
done
[[ -f "$DISPATCH_ROOT/status/{worker_id}.heartbeat" ]] || {{ echo "HEARTBEAT_MISSING"; exit 3; }}
echo HEARTBEAT_PRESENT
ce_stop_heartbeat
[[ -f "$DISPATCH_ROOT/status/{worker_id}.heartbeat" ]] && {{ echo "HEARTBEAT_STALE"; exit 4; }}
echo HEARTBEAT_REMOVED
"""
        env = {
            **os.environ,
            "DISPATCH_ROOT": str(dispatch_root),
            "TMPDIR": str(tmp.name),
        }
        process = subprocess.Popen(
            ["bash", "-c", script],
            cwd=ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        pgid = process.pid
        self.addCleanup(_kill_group_bounded, pgid)
        try:
            stdout, stderr = process.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            _kill_group_bounded(pgid)
            self.fail("normal heartbeat lifecycle did not complete")
        self.assertEqual(process.returncode, 0, stdout + stderr)
        self.assertIn("HEARTBEAT_PRESENT", stdout)
        self.assertIn("HEARTBEAT_REMOVED", stdout)
        # Truthful cancellation: killing the loop must also reap its
        # sleeping child — the whole group drains, nothing is orphaned.
        self.assertTrue(
            _group_drained(pgid),
            "heartbeat loop or its sleep child survived cancellation")


if __name__ == "__main__":
    unittest.main()
