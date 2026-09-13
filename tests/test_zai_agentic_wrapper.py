import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ZaiAgenticWrapperTests(unittest.TestCase):
    def test_zai_defaults_to_glm_53_via_zcode(self):
        wrapper = (ROOT / "bin" / "wrappers" / "zai.sh").read_text()

        self.assertIn("ce_run_zcode", wrapper)
        self.assertNotIn("ANTHROPIC_BASE_URL", wrapper)

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

    def test_zai_uses_zcode_transport(self):
        wrapper = (ROOT / "bin" / "wrappers" / "zai.sh").read_text()
        executor_lib = (ROOT / "bin" / "wrappers" / "_exec.sh").read_text()

        self.assertIn("ce_run_zcode", executor_lib)
        self.assertIn('-p "$CE_FINAL_PROMPT"', executor_lib)
        # Claude Code is no longer the GLM executor transport.
        self.assertNotIn("ce_run_claude", wrapper)
        self.assertNotIn("https://api.z.ai/api/anthropic", wrapper)

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

    def _run_fake_zcode(
        self, *, create_builtin=True, override=None, bundled_override=None
    ):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            resources = root / "ZCode.app" / "Contents" / "Resources"
            builtin = resources / "config" / "provider" / "zcode-builtin.json"
            if create_builtin:
                builtin.parent.mkdir(parents=True)
                builtin.write_text('{}\n')
            fake = root / "zcode"
            fake.write_text(
                "#!/usr/bin/env bash\n"
                "printf 'builtin=%s\\nbundled=%s\\nhome=%s\\n' "
                '"${ZCODE_BUILTIN_PROVIDER_CONFIG_FILE:-}" '
                '"${ZCODE_BUILTIN_PROVIDER_BUNDLED_CONFIG_FILE:-}" '
                '"${HOME:-}"\n'
                "python3 -c 'import json,os; print(\"model=\" + json.load(open(os.path.join(os.environ[\"HOME\"], \".zcode/cli/config.json\")))[\"model\"][\"main\"])'\n"
                "printf 'Status: DONE\\n'\n"
            )
            fake.chmod(0o700)
            flash_home = root / "flash-home"
            config = flash_home / ".zcode" / "cli" / "config.json"
            config.parent.mkdir(parents=True)
            config.write_text('{"model":{"main":"zai/glm-5.3-flash"}}\n')
            env = {
                **os.environ,
                "DISPATCH_ROOT": str(root / "dispatch"),
                "DISPATCH_PACKS_DIR": str(ROOT / "dispatch_packs"),
                "ZCODE_BIN": str(fake),
                "ZCODE_FLASH_HOME": str(flash_home),
                "ZCODE_APP_RESOURCES": str(resources),
            }
            if override is not None:
                env["ZCODE_BUILTIN_PROVIDER_CONFIG_FILE"] = str(override)
            else:
                env.pop("ZCODE_BUILTIN_PROVIDER_CONFIG_FILE", None)
            if bundled_override is not None:
                env["ZCODE_BUILTIN_PROVIDER_BUNDLED_CONFIG_FILE"] = str(
                    bundled_override
                )
            else:
                env.pop("ZCODE_BUILTIN_PROVIDER_BUNDLED_CONFIG_FILE", None)
            output = root / "wrapper-output.txt"
            with output.open("w+") as stream:
                result = subprocess.run(
                    [
                        ROOT / "bin" / "wrappers" / "zai-flash.sh",
                        "--worker-id", "w-zcode-fixture",
                        "--cwd", str(ROOT),
                        "--task", "fixture only",
                    ],
                    cwd=ROOT,
                    env=env,
                    text=True,
                    stdout=stream,
                    stderr=subprocess.STDOUT,
                    timeout=5,
                )
                stream.seek(0)
                captured = stream.read()
            result.stdout = captured
            result.stderr = captured
            return result, builtin, flash_home

    def test_zcode_v2_discovers_installed_resources_config(self):
        result, builtin, flash_home = self._run_fake_zcode()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(f"builtin={builtin}", result.stdout)
        self.assertIn(f"bundled={builtin}", result.stdout)
        self.assertIn(f"home={flash_home}", result.stdout)
        self.assertIn("model=zai/glm-5.3-flash", result.stdout)
        self.assertNotIn("model=auto", result.stdout)

    def test_zcode_v2_preserves_explicit_builtin_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            override = Path(tmp) / "operator-builtin.json"
            override.write_text('{}\n')
            result, _, _ = self._run_fake_zcode(override=override)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(f"builtin={override}", result.stdout)
        self.assertIn(f"bundled={override}", result.stdout)

    def test_zcode_v2_missing_builtin_fails_before_launch(self):
        result, _, _ = self._run_fake_zcode(create_builtin=False)

        self.assertEqual(result.returncode, 69, result.stdout + result.stderr)
        self.assertNotIn("Status: DONE", result.stdout)

    def test_zcode_v2_preserves_distinct_bundled_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundled = Path(tmp) / "operator-bundled.json"
            bundled.write_text('{}\n')
            result, builtin, _ = self._run_fake_zcode(
                bundled_override=bundled
            )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(f"builtin={builtin}", result.stdout)
        self.assertIn(f"bundled={bundled}", result.stdout)

    def test_zcode_v2_missing_bundled_override_fails_before_launch(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing-bundled.json"
            result, _, _ = self._run_fake_zcode(bundled_override=missing)

        self.assertEqual(result.returncode, 69, result.stdout + result.stderr)
        self.assertNotIn("Status: DONE", result.stdout)


if __name__ == "__main__":
    unittest.main()
