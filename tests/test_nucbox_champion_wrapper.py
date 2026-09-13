"""nucbox-champion wrapper receipt gates (2026-09-12, org-hq item 43).

w-8027-task read the old org-bus checkout instead of its assigned worktree and
still finalized phase=done with a dangling log_path, because the wrapper
ignored --cwd, destroyed its output, and hardcoded the terminal status token.
These tests run the real wrapper against a stubbed tokflint (TOKFLINT_DIR)
with a temp DISPATCH_ROOT — no model, no network, no real worker launched.
"""

import json
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WRAPPER = ROOT / "bin" / "wrappers" / "nucbox-champion.sh"

STUB = """#!/usr/bin/env python3
import json, os, sys
with open(os.environ["STUB_OUT"], "a") as f:
    f.write(json.dumps({"stub_cwd": os.getcwd()}) + "\\n")
print("ASST  analysis of the assigned checkout ...")
print("TASK-RECEIVED: " + sys.argv[sys.argv.index("--task") + 1][-400:])
print(os.environ.get("STUB_TAIL", "final answer delivered"))
"""

# A turn that ends without any terminal token: turn_done is not completion.
TOKENLESS_TAIL = "final answer: old checkout lacks candidate EXECUTION-PLAN.md"
DONE_TAIL = "Status: DONE"


class TestChampionWrapperReceipts(unittest.TestCase):
    def _run(self, worker_id, stub_tail, task="Read exact candidate files only."):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        stub_dir = base / "stub"
        assigned = base / "assigned-checkout"
        root = base / "root"
        for d in (stub_dir, assigned, root / "status", root / "logs"):
            d.mkdir(parents=True, exist_ok=True)
        (stub_dir / "tokflint.py").write_text(STUB)
        (stub_dir / "tokflint.py").chmod(0o755)
        stub_out = base / "stub-out.jsonl"

        # Mirror cli.py init_status: status exists before the wrapper runs,
        # advertising the log path whose existence we assert on below.
        status = {
            "schema_version": 3,
            "worker_id": worker_id,
            "mode": "task",
            "executor": "nucbox-champion",
            "current_phase": "starting",
            "pid": 0,
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "tokens_in": 0, "tokens_out": 0, "turns_taken": 0,
            "log_path": str(root / "logs" / f"{worker_id}.log"),
            "brief_path": "", "finalized_at": None,
            "exit_code": None, "error_summary": None,
        }
        (root / "status" / f"{worker_id}.json").write_text(json.dumps(status))

        env = os.environ.copy()
        env.update({
            "DISPATCH_ROOT": str(root),
            "TOKFLINT_DIR": str(stub_dir),
            "STUB_OUT": str(stub_out),
            "STUB_TAIL": stub_tail,
            "CHAMPION_TIMEOUT": "30",
        })
        # DEVNULL mirrors cli.py task start; a captured pipe would block on
        # _exec.sh's orphaned heartbeat sleep (pre-existing, out of scope here).
        proc = subprocess.run(
            ["bash", str(WRAPPER),
             "--worker-id", worker_id,
             "--cwd", str(assigned),
             "--mode", "task",
             "--task", task],
            cwd=str(root),  # dispatcher cwd: deliberately NOT the assignment
            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=120,
        )
        after = json.loads((root / "status" / f"{worker_id}.json").read_text())
        stub_cwd = json.loads(stub_out.read_text().strip())["stub_cwd"]
        return {
            "proc": proc,
            "status": after,
            "stub_cwd": stub_cwd,
            "assigned": assigned,
            "log_path": Path(after["log_path"]),
        }

    def test_tokenless_turn_cannot_finalize_done(self):
        r = self._run("w-43repro-tokenless", TOKENLESS_TAIL)
        self.assertNotEqual(
            r["status"]["current_phase"], "done",
            "turn_done without the worker's terminal token must not be done")
        self.assertEqual(r["status"]["current_phase"], "errored")
        self.assertEqual(r["status"]["exit_code"], 4)
        self.assertIn("terminal status token", r["status"]["error_summary"])

    def test_worker_runs_in_assigned_cwd_not_dispatcher_cwd(self):
        r = self._run("w-43repro-cwd", DONE_TAIL)
        self.assertEqual(
            r["stub_cwd"], str(r["assigned"].resolve()),
            "harness must boot in the dispatched --cwd (wrong-checkout class)")

    def test_done_requires_real_token_and_log_is_retained(self):
        r = self._run("w-43repro-done", DONE_TAIL)
        self.assertEqual(r["proc"].returncode, 0)
        self.assertEqual(r["status"]["current_phase"], "done")
        self.assertTrue(
            r["log_path"].exists(),
            "advertised log_path must exist after completion")
        retained = r["log_path"].read_text()
        self.assertIn("Status: DONE", retained)
        self.assertIn("Output contract", retained,
                      "task handed to the leaf must carry the status protocol")

    def test_nonzero_exit_retains_log_for_diagnosis(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        stub_dir = base / "stub"
        root = base / "root"
        for d in (stub_dir, root / "status", root / "logs"):
            d.mkdir(parents=True, exist_ok=True)
        (stub_dir / "tokflint.py").write_text(
            "#!/usr/bin/env python3\nprint('boom', flush=True)\nraise SystemExit(3)\n")
        (stub_dir / "tokflint.py").chmod(0o755)
        env = os.environ.copy()
        env.update({"DISPATCH_ROOT": str(root), "TOKFLINT_DIR": str(stub_dir),
                    "CHAMPION_TIMEOUT": "30"})
        proc = subprocess.run(
            ["bash", str(WRAPPER), "--worker-id", "w-43repro-crash",
             "--cwd", str(base), "--mode", "task", "--task", "x"],
            cwd=str(base), env=env, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=120)
        log = root / "logs" / "w-43repro-crash.log"
        self.assertEqual(proc.returncode, 3)
        self.assertTrue(log.exists() and log.read_text().strip(),
                        "error evidence must be retained, not deleted")


if __name__ == "__main__":
    unittest.main()
