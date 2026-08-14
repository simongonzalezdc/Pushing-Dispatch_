import os
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ZaiAgenticWrapperTests(unittest.TestCase):
    def test_zai_defaults_to_glm_52(self):
        wrapper = (ROOT / "bin" / "wrappers" / "zai.sh").read_text()

        self.assertIn('ANTHROPIC_MODEL="${ANTHROPIC_MODEL:-glm-5.3}"', wrapper)

    def test_global_launcher_forces_glm_52_without_plaintext_key(self):
        launcher = (ROOT / "bin" / "claude-glm52").read_text()

        self.assertIn("https://api.z.ai/api/anthropic", launcher)
        self.assertIn("glm-5.3", launcher)
        self.assertIn("security find-generic-password", launcher)
        self.assertIn('pass show "pushing-dispatch/$account"', launcher)
        self.assertIn("ANTHROPIC_SMALL_FAST_MODEL", launcher)
        self.assertIn("unset CLAUDE_CODE_OAUTH_TOKEN ANTHROPIC_API_KEY", launcher)
        self.assertIn("glm_api_key", launcher)
        self.assertIn("read-hermes-zai-key", launcher)
        self.assertNotIn('source "$HOME/.hermes/.env"', launcher)
        self.assertNotRegex(launcher, r'''export Z_AI_API_KEY=["'][^$]''')

    def test_zai_uses_agentic_claude_code_transport(self):
        wrapper = (ROOT / "bin" / "wrappers" / "zai.sh").read_text()

        self.assertIn("https://api.z.ai/api/anthropic", wrapper)
        self.assertIn("ANTHROPIC_AUTH_TOKEN", wrapper)
        self.assertIn("ce_run_claude", wrapper)
        self.assertNotIn("ce_run_openai_compatible", wrapper)

    def test_global_launcher_finds_reader_when_invoked_through_symlink(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            hermes = home / ".hermes"
            hermes.mkdir()
            env_file = hermes / ".env"
            env_file.write_text("Z_AI_API_KEY=symlink-key\n")
            env_file.chmod(0o600)
            fake_claude = home / "claude-real"
            fake_claude.write_text(
                "#!/usr/bin/env bash\n"
                "printf '%s|%s' \"${ANTHROPIC_AUTH_TOKEN:-}\" \"${ANTHROPIC_MODEL:-}\"\n"
            )
            fake_claude.chmod(0o700)
            linked_claude = home / "claude"
            linked_claude.symlink_to(ROOT / "bin" / "claude-glm52")

            result = subprocess.run(
                [linked_claude, "--version"],
                env={
                    **os.environ,
                    "HOME": str(home),
                    "CLAUDE_REAL_BIN": str(fake_claude),
                    "ANTHROPIC_AUTH_TOKEN": "",
                    "Z_AI_API_KEY": "",
                },
                text=True,
                capture_output=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "symlink-key|glm-5.3")

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
