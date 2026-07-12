import os
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ZaiAgenticWrapperTests(unittest.TestCase):
    def test_zai_uses_agentic_claude_code_transport(self):
        wrapper = (ROOT / "bin" / "wrappers" / "zai.sh").read_text()

        self.assertIn("https://api.z.ai/api/anthropic", wrapper)
        self.assertIn("ANTHROPIC_AUTH_TOKEN", wrapper)
        self.assertIn("ce_run_claude", wrapper)
        self.assertNotIn("ce_run_openai_compatible", wrapper)

    def test_claude_stream_json_enables_verbose_mode(self):
        executor = (ROOT / "bin" / "wrappers" / "_exec.sh").read_text()

        self.assertIn('''--output-format stream-json
        --verbose''', executor)

    def test_promise_only_output_fails_closed(self):
        script = r'''
source bin/wrappers/_exec.sh
CE_WORKER_ID="w-test"
ce_finalize_status() { printf '%s|%s|%s\n' "$1" "$2" "$3"; }
ce_finalize_from_text "I'll start by reading the handoff document now."
'''
        result = subprocess.run(
            ["bash", "-c", script],
            cwd=ROOT,
            env={**os.environ, "CE_REPO_ROOT": str(ROOT)},
            text=True,
            capture_output=True,
        )

        self.assertEqual(result.returncode, 4, result.stdout + result.stderr)
        self.assertIn("errored|4|missing terminal status token", result.stdout)

    def test_explicit_done_still_succeeds(self):
        script = r'''
source bin/wrappers/_exec.sh
CE_WORKER_ID="w-test"
ce_finalize_status() { printf '%s|%s|%s\n' "$1" "$2" "$3"; }
ce_finalize_from_text $'Work completed.\nStatus: DONE'
'''
        result = subprocess.run(
            ["bash", "-c", script],
            cwd=ROOT,
            env={**os.environ, "CE_REPO_ROOT": str(ROOT)},
            text=True,
            capture_output=True,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("done|0|", result.stdout)


if __name__ == "__main__":
    unittest.main()
