import json
import os
import subprocess
import tempfile
import time
import unittest
import base64
from pathlib import Path
from unittest import mock

from dispatch_lib import nuc_ondemand


def _b64_json(payload):
    return base64.b64encode(
        json.dumps(payload, indent=2).encode("utf-8")
    ).decode("ascii")


def _safe_preflight_output(*, tctl_millic=60000):
    lines = [
        "baseline_active=active",
        "baseline_enabled=enabled",
        "watchdog_active=active",
        "watchdog_enabled=enabled",
        "studio_active=inactive",
        "studio_enabled=disabled",
        "studio_proxy_active=inactive",
        "studio_proxy_enabled=disabled",
        "mutex_active=inactive",
        "gpu_performance_level=low",
        f"tctl_millic={tctl_millic}",
    ]
    for unit in nuc_ondemand.TARGET_UNITS:
        lines.extend((
            f"target:{unit}=inactive",
            f"target_enabled:{unit}=disabled",
        ))
    lines.extend((
        f'lease_b64={_b64_json({"status": "inactive"})}',
        f'catalog_b64={_b64_json({"data": [{"id": nuc_ondemand.BASELINE_MODEL}]})}',
    ))
    return "\n".join(lines)


class NucOnDemandTests(unittest.TestCase):
    def _run_fake_thermal_guard(self, reading, *, fail_disable=False):
        guard = (
            Path(__file__).parents[1]
            / "ops"
            / "unsloth-nucbox"
            / "pushing-dispatch-thermal-guard.sh"
        )
        root = tempfile.TemporaryDirectory()
        self.addCleanup(root.cleanup)
        root_path = Path(root.name)
        hwmon = root_path / "hwmon" / "hwmon0"
        hwmon.mkdir(parents=True)
        (hwmon / "temp1_label").write_text("Tctl\n", encoding="utf-8")
        (hwmon / "temp1_input").write_text(reading, encoding="utf-8")
        fake_bin = root_path / "bin"
        fake_bin.mkdir()
        log = root_path / "commands.log"
        systemctl = fake_bin / "systemctl"
        systemctl.write_text(
            """#!/bin/sh
printf '%s\n' "$*" >>"$GUARD_LOG"
if test "${FAIL_DISABLE:-0}" = 1; then
  case " $* " in *" disable --now "*) exit 1 ;; esac
fi
case " $* " in
  *" is-active "*)
    case "$*" in
      *unsloth-agent-qwen27.service*|*unsloth-agent-qwen27-watchdog.timer*)
        echo active ;;
      *) echo inactive ;;
    esac ;;
  *" is-enabled "*)
    case "$*" in
      *unsloth-agent-qwen27.service*|*unsloth-agent-qwen27-watchdog.timer*)
        echo enabled ;;
      *) echo disabled ;;
    esac ;;
esac
exit 0
""",
            encoding="utf-8",
        )
        sudo = fake_bin / "sudo"
        sudo.write_text(
            "#!/bin/sh\n[ \"${1:-}\" = -n ] && shift\nexec \"$@\"\n",
            encoding="utf-8",
        )
        systemctl.chmod(0o755)
        sudo.chmod(0o755)
        maintenance = root_path / "home" / "unsloth-ops" / "agent_maintenance.py"
        maintenance.parent.mkdir(parents=True)
        maintenance.write_text(
            "#!/bin/sh\nprintf 'maintenance %s\\n' \"$*\" >>\"$GUARD_LOG\"\n",
            encoding="utf-8",
        )
        maintenance.chmod(0o755)
        marker = root_path / "trip"
        env = os.environ.copy()
        env.update({
            "PATH": f"{fake_bin}:/usr/bin:/bin",
            "HOME": str(root_path / "home"),
            "HWMON_ROOT": str(root_path / "hwmon"),
            "THERMAL_SAMPLE_INTERVAL_SECONDS": "0.01",
            "GUARD_LOG": str(log),
            "FAIL_DISABLE": "1" if fail_disable else "0",
        })
        process = subprocess.Popen(
            [str(guard), "90000", str(marker)],
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return process, marker, log

    def test_residency_unit_set_includes_legacy_qwen_boot_collisions(self):
        self.assertEqual(
            nuc_ondemand.TARGET_UNITS,
            (
                "llama-qwen35-35b.service",
                "llama-qwen35-27b.service",
                "qwen36-moe-llama.service",
                "llama-27b.service",
                "llama-mtp.service",
            ),
        )

    def test_systemd_preset_keeps_all_on_demand_units_disabled_at_boot(self):
        preset = (
            Path(__file__).parents[1]
            / "ops"
            / "unsloth-nucbox"
            / "systemd-preset"
            / "90-pushing-dispatch-on-demand.preset"
        ).read_text(encoding="utf-8").splitlines()

        self.assertEqual(
            preset,
            [f"disable {unit}" for unit in nuc_ondemand.TARGET_UNITS],
        )

    def test_resident_service_drop_in_enforces_safe_gpu_power_level(self):
        drop_in = (
            Path(__file__).parents[1]
            / "ops"
            / "unsloth-nucbox"
            / "systemd-user"
            / "unsloth-agent-qwen27.service.d"
            / "10-thermal-power-cap.conf"
        ).read_text(encoding="utf-8")

        self.assertIn("ExecStartPre=", drop_in)
        self.assertIn(nuc_ondemand.GPU_PERFORMANCE_LEVEL_PATH, drop_in)
        self.assertIn("printf low", drop_in)
        self.assertIn('= low', drop_in)

    def test_thermal_guard_fails_safe_to_single_resident_baseline(self):
        guard = (
            Path(__file__).parents[1]
            / "ops"
            / "unsloth-nucbox"
            / "pushing-dispatch-thermal-guard.sh"
        ).read_text(encoding="utf-8")

        self.assertIn("temp*_label", guard)
        self.assertIn("Tctl", guard)
        self.assertIn('test "$tctl_millic" -lt "$limit_millic"', guard)
        self.assertIn("sudo -n systemctl disable --now", guard)
        for unit in nuc_ondemand.TARGET_UNITS:
            self.assertIn(unit, guard)
        self.assertIn("agent_maintenance.py", guard)
        self.assertIn("unsloth-agent-qwen27.service", guard)
        self.assertIn("disable --now unsloth-studio.service", guard)
        self.assertIn("thermal_guard=restore_failed", guard)
        self.assertIn("systemctl is-active", guard)
        self.assertIn("systemctl is-enabled", guard)
        self.assertIn("until restore_single_resident_baseline", guard)
        self.assertIn("HWMON_ROOT", guard)
        self.assertIn("THERMAL_SAMPLE_INTERVAL_SECONDS", guard)
        self.assertIn("power_dpm_force_performance_level", guard)
        self.assertIn("printf low | sudo -n tee", guard)

    def test_thermal_guard_runtime_boundaries_and_unreadable_sensor(self):
        hot, hot_marker, hot_log = self._run_fake_thermal_guard("90000\n")
        _, hot_stderr = hot.communicate(timeout=2)
        self.assertEqual(hot.returncode, 75)
        self.assertIn("reason=limit", hot_marker.read_text(encoding="utf-8"))
        self.assertIn("disable --now", hot_log.read_text(encoding="utf-8"))
        self.assertIn("thermal_guard=tripped", hot_stderr)

        unreadable, unreadable_marker, _ = self._run_fake_thermal_guard("\n")
        unreadable.communicate(timeout=2)
        self.assertEqual(unreadable.returncode, 70)
        self.assertIn(
            "reason=unreadable_tctl",
            unreadable_marker.read_text(encoding="utf-8"),
        )

        below, _, _ = self._run_fake_thermal_guard("89999\n")
        time.sleep(0.05)
        self.assertIsNone(below.poll())
        below.terminate()
        below.communicate(timeout=2)

        failed_restore, _, _ = self._run_fake_thermal_guard(
            "90000\n",
            fail_disable=True,
        )
        time.sleep(0.2)
        self.assertIsNone(failed_restore.poll())
        failed_restore.kill()
        failed_restore.communicate(timeout=2)

    def test_remote_residency_mutex_is_shared_across_dispatch_clients(self):
        self.assertEqual(
            nuc_ondemand.REMOTE_MUTEX_UNIT,
            "pushing-dispatch-nuc-workcell-mutex.service",
        )
        self.assertNotIn(str(os.getpid()), nuc_ondemand.REMOTE_MUTEX_UNIT)

    def test_residency_lock_is_in_user_dispatch_state_not_shared_tmp(self):
        with mock.patch.dict(
            "os.environ",
            {"DISPATCH_ROOT": "/Users/example/.local/share/pushing-dispatch"},
        ):
            lock_path = nuc_ondemand._residency_lock_path()

        self.assertEqual(
            lock_path,
            Path("/Users/example/.local/share/pushing-dispatch/state/nuc-ondemand.lock"),
        )
        self.assertNotEqual(lock_path.parent, Path("/tmp"))

    def test_remote_backend_always_binds_the_user_systemd_bus(self):
        completed = mock.Mock(returncode=0, stdout="ok\n", stderr="")
        with mock.patch(
            "dispatch_lib.nuc_ondemand.subprocess.run",
            return_value=completed,
        ) as run:
            backend = nuc_ondemand.RemoteBackend("nuc.example")
            self.assertEqual(backend._ssh("systemctl --user is-active example.service"), "ok\n")

        script = run.call_args.kwargs["input"]
        self.assertIn("XDG_RUNTIME_DIR=/run/user/$(id -u)", script)
        self.assertIn("DBUS_SESSION_BUS_ADDRESS=unix:path=$XDG_RUNTIME_DIR/bus", script)

    def test_profiles_pin_exact_model_runtime_and_role(self):
        general = nuc_ondemand.PROFILES["qwen35-35b-general"]
        review = nuc_ondemand.PROFILES["qwen35-27b-review"]
        coding = nuc_ondemand.PROFILES["qwen36-35b-coding"]

        self.assertEqual(general.expected_model, "Qwen3.5-35B-A3B-Q4_K_M.gguf")
        self.assertEqual(
            general.model_sha256,
            "3b46d1066bc91cc2d613e3bc22ce691dd77e6f0d33c9060690d24ce6de494375",
        )
        self.assertEqual(general.tools, ("read", "grep", "find", "ls"))
        self.assertEqual(review.tools, ("read",))
        self.assertEqual(review.context_window, 32768)
        self.assertEqual(review.max_output_tokens, 512)
        self.assertEqual(coding.expected_model, "qwen3.6:35b")
        self.assertEqual(
            coding.model_sha256,
            "4ac6a06bce551257267f49ad2226f8671a22519ccc1a4dde9d5b433d1f2a410d",
        )
        self.assertEqual(coding.tools, ("read", "bash", "edit"))
        self.assertEqual(coding.context_window, 32768)
        self.assertEqual(coding.max_output_tokens, 1024)

    def test_oversized_coding_request_fails_before_nuc_residency_changes(self):
        profile = nuc_ondemand.PROFILES["qwen36-35b-coding"]
        backend = mock.Mock()
        backend.preflight.return_value = {"restoration_ready": True}
        backend.identity.return_value = {
            "model": profile.expected_model,
            "model_path": profile.model_path,
            "model_sha256": profile.model_sha256,
            "runtime_path": profile.runtime_path,
            "runtime_sha256": profile.runtime_sha256,
            "context_window": profile.context_window,
        }
        backend.api_key.return_value = ""
        backend.verify_restored.return_value = {"restored": True}

        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            prompt = root_path / "prompt.txt"
            prompt.write_text("x" * 30_000, encoding="utf-8")
            with self.assertRaisesRegex(
                nuc_ondemand.WorkcellError,
                "estimated request .* exceeds 32768-token context",
            ):
                nuc_ondemand.run_workcell(
                    profile,
                    prompt=prompt,
                    cwd=root_path,
                    log_file=root_path / "run.log",
                    receipt_file=root_path / "receipt.json",
                    backend=backend,
                    pi_runner=mock.Mock(return_value=(0, "Status: DONE\n")),
                )

        backend.preflight.assert_not_called()
        backend.acquire.assert_not_called()
        backend.activate.assert_not_called()

    def test_oversized_review_request_fails_before_nuc_residency_changes(self):
        profile = nuc_ondemand.PROFILES["qwen35-27b-review"]
        backend = mock.Mock()
        backend.preflight.return_value = {"restoration_ready": True}
        backend.identity.return_value = {
            "model": profile.expected_model,
            "model_path": profile.model_path,
            "model_sha256": profile.model_sha256,
            "runtime_path": profile.runtime_path,
            "runtime_sha256": profile.runtime_sha256,
            "context_window": profile.context_window,
        }
        backend.api_key.return_value = ""
        backend.verify_restored.return_value = {"restored": True}

        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            prompt = root_path / "prompt.txt"
            prompt.write_text("x" * 33_000, encoding="utf-8")
            with self.assertRaisesRegex(
                nuc_ondemand.WorkcellError,
                "estimated request .* exceeds 32768-token context",
            ):
                nuc_ondemand.run_workcell(
                    profile,
                    prompt=prompt,
                    cwd=root_path,
                    log_file=root_path / "run.log",
                    receipt_file=root_path / "receipt.json",
                    backend=backend,
                    pi_runner=mock.Mock(return_value=(0, "Status: DONE\n")),
                )

        backend.preflight.assert_not_called()
        backend.acquire.assert_not_called()
        backend.activate.assert_not_called()

    def test_qwen35_general_uses_governed_32k_context_launcher(self):
        general = nuc_ondemand.PROFILES["qwen35-35b-general"]
        launcher = (
            Path(__file__).parents[1]
            / "ops"
            / "unsloth-nucbox"
            / "launchers"
            / "start-qwen35-35b.sh"
        ).read_text(encoding="utf-8")

        self.assertEqual(general.context_window, 32768)
        self.assertIn("-c 32768 -np 1", launcher)
        self.assertNotIn("-c 8192", launcher)

    def test_qwen35_general_launcher_caps_prompt_compute_for_thermal_headroom(self):
        launcher = (
            Path(__file__).parents[1]
            / "ops"
            / "unsloth-nucbox"
            / "launchers"
            / "start-qwen35-35b.sh"
        ).read_text(encoding="utf-8")

        self.assertIn("-t 8 -tb 8", launcher)
        self.assertIn("-b 512 -ub 128", launcher)

    def test_qwen36_coding_drop_in_launches_the_governed_32k_context(self):
        drop_in = (
            Path(__file__).parents[1]
            / "ops"
            / "unsloth-nucbox"
            / "systemd"
            / "qwen36-moe-llama.service.d"
            / "20-context-window.conf"
        ).read_text(encoding="utf-8")

        self.assertIn("ExecStart=", drop_in)
        self.assertIn("--ctx-size 32768", drop_in)
        self.assertNotIn("--ctx-size 16384", drop_in)
        self.assertNotIn("--ctx-size 8192", drop_in)
        self.assertIn("--threads 8 --threads-batch 8", drop_in)
        self.assertIn("--batch-size 512 --ubatch-size 128", drop_in)

    def test_qwen35_review_drop_in_launches_the_governed_32k_context(self):
        drop_in = (
            Path(__file__).parents[1]
            / "ops"
            / "unsloth-nucbox"
            / "systemd"
            / "llama-qwen35-27b.service.d"
            / "20-context-window.conf"
        ).read_text(encoding="utf-8")

        self.assertIn("ExecStart=", drop_in)
        self.assertIn("-c 32768 -np 1", drop_in)
        self.assertNotIn("-c 8192", drop_in)

    def test_pi_runner_keeps_full_context_but_uses_each_profile_output_cap(self):
        expected_caps = {
            "qwen35-35b-general": 2048,
            "qwen35-27b-review": 512,
            "qwen36-35b-coding": 1024,
        }
        for profile_name, expected_cap in expected_caps.items():
            with self.subTest(profile=profile_name):
                profile = nuc_ondemand.PROFILES[profile_name]
                captured = {}

                def complete(command, **kwargs):
                    model_config = (
                        Path(kwargs["env"]["PI_CODING_AGENT_DIR"]) / "models.json"
                    )
                    captured.update(
                        json.loads(model_config.read_text(encoding="utf-8"))
                    )
                    return mock.Mock(returncode=0, stdout="Status: DONE\n")

                with tempfile.TemporaryDirectory() as root:
                    root_path = Path(root)
                    prompt = root_path / "prompt.txt"
                    prompt.write_text("Perform one bounded task.", encoding="utf-8")
                    with mock.patch(
                        "dispatch_lib.nuc_ondemand.subprocess.run",
                        side_effect=complete,
                    ):
                        code, _ = nuc_ondemand.default_pi_runner(
                            profile,
                            prompt,
                            root_path,
                            root_path / "run.log",
                            "test-key",
                        )

                model = captured["providers"][profile.name]["models"][0]
                self.assertEqual(code, 0)
                self.assertEqual(model["contextWindow"], profile.context_window)
                self.assertEqual(model["maxTokens"], expected_cap)

    def test_identity_rejects_a_ready_wrong_model_without_retrying_or_hashing(self):
        profile = nuc_ondemand.PROFILES["qwen35-35b-general"]
        backend = nuc_ondemand.RemoteBackend("nuc.example")
        backend._ssh = mock.Mock(return_value=json.dumps({
            "data": [{"id": "not-the-pinned-model"}],
        }))

        with mock.patch("dispatch_lib.nuc_ondemand.time.sleep") as sleep:
            with self.assertRaisesRegex(nuc_ondemand.WorkcellError, "model identity"):
                backend.identity(profile)

        backend._ssh.assert_called_once()
        sleep.assert_not_called()

    def test_identity_rejects_wrong_advertised_context_without_hashing(self):
        profile = nuc_ondemand.PROFILES["qwen35-35b-general"]
        backend = nuc_ondemand.RemoteBackend("nuc.example")
        backend._ssh = mock.Mock(return_value=json.dumps({
            "data": [{
                "id": profile.expected_model,
                "meta": {"n_ctx": profile.context_window * 4},
            }],
        }))

        with self.assertRaisesRegex(nuc_ondemand.WorkcellError, "context"):
            backend.identity(profile)

        backend._ssh.assert_called_once()

    def test_identity_readiness_is_bounded_by_elapsed_time(self):
        profile = nuc_ondemand.PROFILES["qwen35-35b-general"]
        backend = nuc_ondemand.RemoteBackend("nuc.example")
        backend._ssh = mock.Mock(side_effect=nuc_ondemand.WorkcellError("not ready"))

        with mock.patch.object(nuc_ondemand, "IDENTITY_READY_TIMEOUT_SECONDS", 1):
            with mock.patch(
                "dispatch_lib.nuc_ondemand.time.monotonic",
                side_effect=[10.0, 10.5, 11.1],
            ):
                with mock.patch("dispatch_lib.nuc_ondemand.time.sleep") as sleep:
                    with self.assertRaisesRegex(
                        nuc_ondemand.WorkcellError,
                        "identity deadline",
                    ):
                        backend.identity(profile)

        backend._ssh.assert_called_once()
        sleep.assert_called_once_with(3)

    def test_identity_binds_digests_to_the_active_service_process(self):
        profile = nuc_ondemand.PROFILES["qwen35-35b-general"]
        backend = nuc_ondemand.RemoteBackend("nuc.example")
        backend._ssh = mock.Mock(side_effect=[
            json.dumps({
                "data": [{
                    "id": profile.expected_model,
                    "meta": {"n_ctx": profile.context_window},
                }],
            }),
            "\n".join([
                f"runtime_path={profile.runtime_path}",
                f"model_path={profile.model_path}",
                f"runtime_sha256={profile.runtime_sha256}",
                f"model_sha256={profile.model_sha256}",
            ]),
        ])

        identity = backend.identity(profile)

        self.assertEqual(identity["runtime_path"], profile.runtime_path)
        self.assertEqual(identity["model_path"], profile.model_path)
        process_script = backend._ssh.call_args_list[1].args[0]
        self.assertIn("MainPID", process_script)
        self.assertIn("/proc/$pid/exe", process_script)
        self.assertIn("/proc/$pid/cmdline", process_script)
        self.assertIn('sha256sum "$runtime_path"', process_script)
        self.assertIn('sha256sum "$model_path"', process_script)

    def test_identity_rejects_profile_file_that_is_not_the_running_model(self):
        profile = nuc_ondemand.PROFILES["qwen35-35b-general"]
        backend = nuc_ondemand.RemoteBackend("nuc.example")
        backend._ssh = mock.Mock(side_effect=[
            json.dumps({
                "data": [{
                    "id": profile.expected_model,
                    "meta": {"n_ctx": profile.context_window},
                }],
            }),
            "\n".join([
                f"runtime_path={profile.runtime_path}",
                "model_path=/srv/external/models/gguf/Qwen3.5/wrong.gguf",
                f"runtime_sha256={profile.runtime_sha256}",
                f"model_sha256={profile.model_sha256}",
            ]),
        ])

        with self.assertRaisesRegex(nuc_ondemand.WorkcellError, "model process path"):
            backend.identity(profile)

    def test_json_value_decodes_pretty_multiline_payload_from_base64(self):
        payload = {"status": "inactive", "nested": {"owner": None}}
        encoded = base64.b64encode(
            json.dumps(payload, indent=2).encode("utf-8")
        ).decode("ascii")

        self.assertEqual(
            nuc_ondemand._json_value({"lease_b64": encoded}, "lease"),
            payload,
        )

    def test_activate_safety_timer_has_direct_baseline_start_fallback(self):
        profile = nuc_ondemand.PROFILES["qwen35-35b-general"]
        backend = nuc_ondemand.RemoteBackend("nuc.example")
        backend._ssh = mock.Mock(return_value="")

        backend.activate(profile)

        script = backend._ssh.call_args.args[0]
        self.assertIn("systemctl disable --now", script)
        for unit in nuc_ondemand.TARGET_UNITS:
            self.assertIn(unit, script)
        self.assertIn("agent_maintenance.py end || systemctl --user enable --now", script)
        self.assertIn("unsloth-agent-qwen27.service", script)
        self.assertIn(
            "systemctl --user disable --now unsloth-studio.service "
            "unsloth-openai-proxy.service",
            script,
        )
        self.assertNotIn("systemctl --user restart unsloth-studio.service", script)
        self.assertNotIn("systemctl --user start unsloth-openai-proxy.service", script)

    def test_activate_safety_timer_self_collects_without_releasing_mutex(self):
        profile = nuc_ondemand.PROFILES["qwen35-35b-general"]
        backend = nuc_ondemand.RemoteBackend("nuc.example")
        backend._ssh = mock.Mock(return_value="")

        backend.activate(profile)

        script = backend._ssh.call_args.args[0]
        self.assertIn(
            f"systemd-run --user --collect --unit={backend.auto_restore_unit}",
            script,
        )
        self.assertNotIn(
            f"systemctl --user stop {nuc_ondemand.REMOTE_MUTEX_UNIT}",
            script,
        )

    def test_activation_starts_bounded_thermal_guard_before_target(self):
        profile = nuc_ondemand.PROFILES["qwen35-35b-general"]
        backend = nuc_ondemand.RemoteBackend("nuc.example")
        backend._ssh = mock.Mock(return_value="")

        backend.activate(profile)

        script = backend._ssh.call_args.args[0]
        guard = script.index(
            f"systemd-run --user --collect --unit={backend.thermal_guard_unit}"
        )
        target = script.index(f"sudo -n systemctl start {profile.service}")
        self.assertLess(guard, target)
        self.assertIn("RuntimeMaxSec=35m", script)
        self.assertIn(nuc_ondemand.THERMAL_GUARD_PATH, script)
        self.assertIn(str(nuc_ondemand.MAX_RUNTIME_TCTL_MILLIC), script)
        self.assertGreaterEqual(
            script.count(
                f"systemctl --user is-active {backend.auto_restore_unit}.timer"
            ),
            2,
        )
        self.assertGreater(
            script.rfind(
                f"systemctl --user is-active {backend.thermal_guard_unit}",
                0,
                target,
            ),
            guard,
        )
        self.assertIn(
            f"systemctl --user is-active {backend.thermal_guard_unit}",
            script[target:],
        )
        self.assertIn(
            f"sudo -n systemctl disable --now {profile.service}",
            script[target:],
        )
        self.assertLess(
            script.index(
                f"printf low | sudo -n tee "
                f"{nuc_ondemand.GPU_PERFORMANCE_LEVEL_PATH}"
            ),
            target,
        )
        self.assertIn(
            f'test "$(cat {nuc_ondemand.GPU_PERFORMANCE_LEVEL_PATH})" = low',
            script,
        )

    def test_verified_cleanup_cancels_thermal_guard_with_restore_timer(self):
        profile = nuc_ondemand.PROFILES["qwen35-35b-general"]
        backend = nuc_ondemand.RemoteBackend("nuc.example")
        backend._ssh = mock.Mock(return_value="")

        backend.cancel_auto_restore(profile)

        script = backend._ssh.call_args.args[0]
        self.assertIn(f"{backend.auto_restore_unit}.timer", script)
        self.assertIn(f"{backend.thermal_guard_unit}.service", script)

    def test_remote_thermal_trip_reads_pid_scoped_marker(self):
        profile = nuc_ondemand.PROFILES["qwen35-35b-general"]
        backend = nuc_ondemand.RemoteBackend("nuc.example")
        backend._ssh = mock.Mock(return_value="reason=limit tctl_millic=90000\n")

        trip = backend.thermal_trip(profile)

        self.assertEqual(trip, "reason=limit tctl_millic=90000")
        self.assertIn(backend.thermal_guard_unit, backend._ssh.call_args.args[0])

    def test_remote_acquire_rechecks_targets_and_all_restore_timers(self):
        profile = nuc_ondemand.PROFILES["qwen35-35b-general"]
        backend = nuc_ondemand.RemoteBackend("nuc.example")
        backend._ssh = mock.Mock(return_value="")

        backend.acquire(profile)

        script = backend._ssh.call_args.args[0]
        self.assertIn(nuc_ondemand.REMOTE_MUTEX_UNIT, script)
        self.assertIn("RuntimeMaxSec=35m", script)
        self.assertIn("pushing-dispatch-nuc-restore-*", script)
        self.assertIn("pushing-dispatch-nuc-thermal-guard-*", script)
        self.assertIn("json.load(sys.stdin)", script)
        self.assertNotIn("grep -Fq", script)
        for unit in nuc_ondemand.TARGET_UNITS:
            self.assertIn(unit, script)
            self.assertIn(f"systemctl is-enabled {unit}", script)

    def test_activation_quiesces_the_studio_proxy_before_starting_target(self):
        profile = nuc_ondemand.PROFILES["qwen35-35b-general"]
        backend = nuc_ondemand.RemoteBackend("nuc.example")
        backend._ssh = mock.Mock(return_value="")

        backend.activate(profile)

        script = backend._ssh.call_args.args[0]
        stop_proxy = script.index(
            "systemctl --user disable --now unsloth-studio.service "
            "unsloth-openai-proxy.service"
        )
        start_target = script.index(f"sudo -n systemctl start {profile.service}")
        self.assertLess(stop_proxy, start_target)

    def test_activation_never_restarts_or_unloads_the_studio_lane(self):
        profile = nuc_ondemand.PROFILES["qwen35-35b-general"]
        backend = nuc_ondemand.RemoteBackend("nuc.example")
        backend._ssh = mock.Mock(return_value="")

        backend.activate(profile)

        script = backend._ssh.call_args.args[0]
        self.assertNotIn("/api/inference/unload", script)
        self.assertNotIn("systemctl --user restart unsloth-studio.service", script)
        self.assertNotIn("systemctl --user start unsloth-openai-proxy.service", script)

    def test_preflight_rejects_an_unknown_studio_model_resident(self):
        profile = nuc_ondemand.PROFILES["qwen35-35b-general"]
        backend = nuc_ondemand.RemoteBackend("nuc.example")
        backend._ssh = mock.Mock(return_value="\n".join([
            "baseline_active=active",
            "baseline_enabled=enabled",
            "watchdog_active=active",
            "watchdog_enabled=enabled",
            "studio_proxy_active=active",
            "studio_proxy_enabled=enabled",
            "mutex_active=inactive",
            "target:llama-qwen35-35b.service=inactive",
            "target:llama-qwen35-27b.service=inactive",
            "target:qwen36-moe-llama.service=inactive",
            'lease={"status":"inactive"}',
            'studio_status={"active_model":"a-user-selected-model"}',
            'catalog={"data":[{"id":"unsloth/Qwen3.6-27B-MTP-GGUF"}]}',
        ]))

        with self.assertRaisesRegex(nuc_ondemand.WorkcellError, "preflight"):
            backend.preflight(profile)

        script = backend._ssh.call_args.args[0]
        self.assertNotIn("/api/inference/status", script)
        self.assertNotIn("agent_api_key", script)

    def test_preflight_rejects_even_the_known_duplicate_studio_model(self):
        profile = nuc_ondemand.PROFILES["qwen35-35b-general"]
        backend = nuc_ondemand.RemoteBackend("nuc.example")
        backend._ssh = mock.Mock(return_value="\n".join([
            "baseline_active=active",
            "baseline_enabled=enabled",
            "watchdog_active=active",
            "watchdog_enabled=enabled",
            "studio_proxy_active=active",
            "studio_proxy_enabled=enabled",
            "mutex_active=inactive",
            "target:llama-qwen35-35b.service=inactive",
            "target_enabled:llama-qwen35-35b.service=disabled",
            "target:llama-qwen35-27b.service=inactive",
            "target_enabled:llama-qwen35-27b.service=disabled",
            "target:qwen36-moe-llama.service=inactive",
            "target_enabled:qwen36-moe-llama.service=disabled",
            "target:llama-27b.service=inactive",
            "target_enabled:llama-27b.service=disabled",
            "target:llama-mtp.service=inactive",
            "target_enabled:llama-mtp.service=disabled",
            'lease={"status":"inactive"}',
            'studio_status={"active_model":"unsloth/Qwen3.6-27B-MTP-GGUF"}',
            'catalog={"data":[{"id":"unsloth/Qwen3.6-27B-MTP-GGUF"}]}',
        ]))

        with self.assertRaisesRegex(nuc_ondemand.WorkcellError, "preflight"):
            backend.preflight(profile)

    def test_preflight_rejects_current_cpu_temperature_above_limit(self):
        profile = nuc_ondemand.PROFILES["qwen35-35b-general"]
        backend = nuc_ondemand.RemoteBackend("nuc.example")
        backend._ssh = mock.Mock(return_value=_safe_preflight_output(tctl_millic=85001))

        with self.assertRaisesRegex(nuc_ondemand.WorkcellError, "preflight"):
            backend.preflight(profile)

        script = backend._ssh.call_args.args[0]
        self.assertIn("/sys/class/hwmon", script)
        self.assertIn("temp*_label", script)
        self.assertIn("Tctl", script)

    def test_preflight_admits_cpu_temperature_at_exact_limit(self):
        profile = nuc_ondemand.PROFILES["qwen35-35b-general"]
        backend = nuc_ondemand.RemoteBackend("nuc.example")
        backend._ssh = mock.Mock(return_value=_safe_preflight_output(tctl_millic=85000))

        self.assertTrue(backend.preflight(profile)["restoration_ready"])

    def test_preflight_rejects_unrestricted_gpu_power_level(self):
        profile = nuc_ondemand.PROFILES["qwen35-35b-general"]
        output = _safe_preflight_output().replace(
            "gpu_performance_level=low",
            "gpu_performance_level=auto",
        )
        backend = nuc_ondemand.RemoteBackend("nuc.example")
        backend._ssh = mock.Mock(return_value=output)

        with self.assertRaisesRegex(nuc_ondemand.WorkcellError, "preflight"):
            backend.preflight(profile)

    def test_preflight_rejects_missing_or_non_numeric_cpu_temperature(self):
        profile = nuc_ondemand.PROFILES["qwen35-35b-general"]
        for reading in ("", "not-a-number"):
            with self.subTest(reading=reading):
                output = _safe_preflight_output()
                output = output.replace("tctl_millic=60000", f"tctl_millic={reading}")
                backend = nuc_ondemand.RemoteBackend("nuc.example")
                backend._ssh = mock.Mock(return_value=output)

                with self.assertRaisesRegex(nuc_ondemand.WorkcellError, "preflight"):
                    backend.preflight(profile)

    def test_preflight_admits_only_single_resident_with_studio_disabled(self):
        profile = nuc_ondemand.PROFILES["qwen35-35b-general"]
        backend = nuc_ondemand.RemoteBackend("nuc.example")
        backend._ssh = mock.Mock(return_value=_safe_preflight_output())

        result = backend.preflight(profile)

        self.assertTrue(result["restoration_ready"])
        script = backend._ssh.call_args.args[0]
        self.assertIn(
            "systemctl --user is-active unsloth-studio.service || true",
            script,
        )
        self.assertIn(
            "systemctl --user is-enabled unsloth-studio.service || true",
            script,
        )
        self.assertIn(
            "systemctl --user is-active unsloth-openai-proxy.service || true",
            script,
        )
        self.assertIn(
            "systemctl --user is-enabled unsloth-openai-proxy.service || true",
            script,
        )

    def test_preflight_rejects_an_inactive_but_enabled_target_unit(self):
        profile = nuc_ondemand.PROFILES["qwen35-35b-general"]
        backend = nuc_ondemand.RemoteBackend("nuc.example")
        backend._ssh = mock.Mock(return_value="\n".join([
            "baseline_active=active",
            "baseline_enabled=enabled",
            "watchdog_active=active",
            "watchdog_enabled=enabled",
            "studio_proxy_active=active",
            "studio_proxy_enabled=enabled",
            "mutex_active=inactive",
            "target:llama-qwen35-35b.service=inactive",
            "target_enabled:llama-qwen35-35b.service=disabled",
            "target:llama-qwen35-27b.service=inactive",
            "target_enabled:llama-qwen35-27b.service=enabled",
            "target:qwen36-moe-llama.service=inactive",
            "target_enabled:qwen36-moe-llama.service=disabled",
            "target:llama-27b.service=inactive",
            "target_enabled:llama-27b.service=disabled",
            "target:llama-mtp.service=inactive",
            "target_enabled:llama-mtp.service=disabled",
            'lease={"status":"inactive"}',
            'studio_status={"active_model":null}',
            'catalog={"data":[{"id":"unsloth/Qwen3.6-27B-MTP-GGUF"}]}',
        ]))

        with self.assertRaisesRegex(nuc_ondemand.WorkcellError, "preflight"):
            backend.preflight(profile)

        script = backend._ssh.call_args.args[0]
        for unit in nuc_ondemand.TARGET_UNITS:
            self.assertIn(f"systemctl is-enabled {unit}", script)

    def test_activation_disables_duplicate_lane_before_target_start(self):
        profile = nuc_ondemand.PROFILES["qwen36-35b-coding"]
        backend = nuc_ondemand.RemoteBackend("nuc.example")
        backend._ssh = mock.Mock(return_value="")

        backend.activate(profile)

        script = backend._ssh.call_args.args[0]
        disable_duplicate = script.index(
            "systemctl --user disable --now unsloth-studio.service "
            "unsloth-openai-proxy.service"
        )
        start_target = script.index(f"sudo -n systemctl start {profile.service}")
        self.assertLess(disable_duplicate, start_target)
        self.assertNotIn("/api/inference/unload", script)

    def test_verify_restored_requires_single_resident_and_disabled_studio_lane(self):
        profile = nuc_ondemand.PROFILES["qwen35-27b-review"]
        backend = nuc_ondemand.RemoteBackend("nuc.example")
        output = "\n".join([
            "baseline_active=active",
            "baseline_enabled=enabled",
            "watchdog_active=active",
            "watchdog_enabled=enabled",
            "studio_active=inactive",
            "studio_enabled=disabled",
            "studio_proxy_active=inactive",
            "studio_proxy_enabled=disabled",
            "mutex_active=active",
            "gpu_performance_level=low",
            "target:llama-qwen35-35b.service=inactive",
            "target_enabled:llama-qwen35-35b.service=disabled",
            "target:llama-qwen35-27b.service=inactive",
            "target_enabled:llama-qwen35-27b.service=disabled",
            "target:qwen36-moe-llama.service=inactive",
            "target_enabled:qwen36-moe-llama.service=disabled",
            "target:llama-27b.service=inactive",
            "target_enabled:llama-27b.service=disabled",
            "target:llama-mtp.service=inactive",
            "target_enabled:llama-mtp.service=disabled",
            f'lease_b64={_b64_json({"status": "inactive"})}',
            f'catalog_b64={_b64_json({"data": [{"id": nuc_ondemand.BASELINE_MODEL}]})}',
        ])
        backend._ssh = mock.Mock(return_value=output)

        restored = backend.verify_restored(profile)

        self.assertTrue(restored["restored"])
        script = backend._ssh.call_args.args[0]
        self.assertIn("for attempt in $(seq 1", script)
        self.assertIn("sleep 3", script)
        self.assertIn("curl -fsS", script)
        self.assertNotIn("/api/inference/status", script)
        self.assertIn("is-active unsloth-studio.service", script)
        self.assertIn("is-enabled unsloth-studio.service", script)

    def test_restore_disables_all_on_demand_units(self):
        profile = nuc_ondemand.PROFILES["qwen35-27b-review"]
        backend = nuc_ondemand.RemoteBackend("nuc.example")
        backend._ssh = mock.Mock(return_value="")

        backend.restore(profile)

        script = backend._ssh.call_args.args[0]
        self.assertIn("systemctl disable --now", script)
        self.assertIn("systemctl reset-failed", script)
        self.assertIn(
            "systemctl --user disable --now unsloth-studio.service "
            "unsloth-openai-proxy.service",
            script,
        )
        self.assertNotIn("systemctl --user restart unsloth-studio.service", script)
        self.assertNotIn("systemctl --user start unsloth-openai-proxy.service", script)
        self.assertIn(
            f"printf low | sudo -n tee "
            f"{nuc_ondemand.GPU_PERFORMANCE_LEVEL_PATH}",
            script,
        )
        self.assertIn(
            'test "$stop_rc" -eq 0 -a "$reset_rc" -eq 0 -a "$gpu_rc" -eq 0 '
            '-a "$end_rc" -eq 0 -a "$studio_rc" -eq 0',
            script,
        )
        for unit in nuc_ondemand.TARGET_UNITS:
            self.assertIn(unit, script)

    def test_verify_restored_rejects_unknown_studio_model(self):
        profile = nuc_ondemand.PROFILES["qwen35-27b-review"]
        backend = nuc_ondemand.RemoteBackend("nuc.example")
        output = "\n".join([
            "baseline_active=active",
            "baseline_enabled=enabled",
            "watchdog_active=active",
            "watchdog_enabled=enabled",
            "studio_proxy_active=active",
            "studio_proxy_enabled=enabled",
            "mutex_active=active",
            "target:llama-qwen35-35b.service=inactive",
            "target:llama-qwen35-27b.service=inactive",
            "target:qwen36-moe-llama.service=inactive",
            f'lease_b64={_b64_json({"status": "inactive"})}',
            f'studio_status_b64={_b64_json({"active_model": "unexpected-model"})}',
            f'catalog_b64={_b64_json({"data": [{"id": nuc_ondemand.BASELINE_MODEL}]})}',
        ])
        backend._ssh = mock.Mock(return_value=output)

        restored = backend.verify_restored(profile)

        self.assertFalse(restored["restored"])

    def test_verify_restored_rejects_an_enabled_on_demand_unit(self):
        profile = nuc_ondemand.PROFILES["qwen35-27b-review"]
        backend = nuc_ondemand.RemoteBackend("nuc.example")
        output = "\n".join([
            "baseline_active=active",
            "baseline_enabled=enabled",
            "watchdog_active=active",
            "watchdog_enabled=enabled",
            "studio_proxy_active=active",
            "studio_proxy_enabled=enabled",
            "mutex_active=active",
            "target:llama-qwen35-35b.service=inactive",
            "target_enabled:llama-qwen35-35b.service=disabled",
            "target:llama-qwen35-27b.service=inactive",
            "target_enabled:llama-qwen35-27b.service=enabled",
            "target:qwen36-moe-llama.service=inactive",
            "target_enabled:qwen36-moe-llama.service=disabled",
            "target:llama-27b.service=inactive",
            "target_enabled:llama-27b.service=disabled",
            "target:llama-mtp.service=inactive",
            "target_enabled:llama-mtp.service=disabled",
            f'lease_b64={_b64_json({"status": "inactive"})}',
            f'studio_status_b64={_b64_json({"active_model": None})}',
            f'catalog_b64={_b64_json({"data": [{"id": nuc_ondemand.BASELINE_MODEL}]})}',
        ])
        backend._ssh = mock.Mock(return_value=output)

        restored = backend.verify_restored(profile)

        self.assertFalse(restored["restored"])

    def test_identity_mismatch_fails_and_restores_before_return(self):
        profile = nuc_ondemand.PROFILES["qwen35-35b-general"]
        events = []
        backend = mock.Mock()
        backend.preflight.return_value = {"restoration_ready": True}
        backend.activate.side_effect = lambda value: events.append(("activate", value.name))
        backend.identity.return_value = {
            "model": "wrong-model",
            "model_path": profile.model_path,
            "model_sha256": profile.model_sha256,
            "runtime_path": profile.runtime_path,
            "runtime_sha256": profile.runtime_sha256,
            "context_window": profile.context_window,
        }
        backend.restore.side_effect = lambda value: events.append(("restore", value.name))
        backend.verify_restored.return_value = {"restored": True}

        with tempfile.TemporaryDirectory() as root:
            prompt = Path(root) / "prompt.txt"
            prompt.write_text("Summarize this.", encoding="utf-8")
            with self.assertRaisesRegex(nuc_ondemand.WorkcellError, "model identity"):
                nuc_ondemand.run_workcell(
                    profile,
                    prompt=prompt,
                    cwd=Path(root),
                    log_file=Path(root) / "run.log",
                    receipt_file=Path(root) / "receipt.json",
                    backend=backend,
                    pi_runner=mock.Mock(),
                )

        self.assertEqual(events, [
            ("activate", profile.name),
            ("restore", profile.name),
        ])
        backend.verify_restored.assert_called_once_with(profile)

    def test_partial_activation_failure_still_runs_immediate_restoration(self):
        profile = nuc_ondemand.PROFILES["qwen35-35b-general"]
        backend = mock.Mock()
        backend.preflight.return_value = {"restoration_ready": True}
        backend.activate.side_effect = nuc_ondemand.WorkcellError(
            "activation command lost its connection"
        )
        backend.verify_restored.return_value = {"restored": True}

        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            prompt = root_path / "prompt.txt"
            prompt.write_text("Summarize this.", encoding="utf-8")
            with self.assertRaisesRegex(nuc_ondemand.WorkcellError, "activation"):
                nuc_ondemand.run_workcell(
                    profile,
                    prompt=prompt,
                    cwd=root_path,
                    log_file=root_path / "run.log",
                    receipt_file=root_path / "receipt.json",
                    backend=backend,
                    pi_runner=mock.Mock(),
                )
            payload = json.loads(
                (root_path / "receipt.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                payload["failure_detail"],
                "activation command lost its connection",
            )

        backend.restore.assert_called_once_with(profile)
        backend.verify_restored.assert_called_once_with(profile)

    def test_failed_remote_acquire_does_not_restore_another_owners_workcell(self):
        profile = nuc_ondemand.PROFILES["qwen35-35b-general"]
        backend = mock.Mock()
        backend.preflight.return_value = {"restoration_ready": True}
        backend.acquire.side_effect = nuc_ondemand.WorkcellBusy(
            "remote residency mutex is already held"
        )

        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            prompt = root_path / "prompt.txt"
            prompt.write_text("Review this.", encoding="utf-8")
            with self.assertRaisesRegex(nuc_ondemand.WorkcellBusy, "mutex"):
                nuc_ondemand.run_workcell(
                    profile,
                    prompt=prompt,
                    cwd=root_path,
                    log_file=root_path / "run.log",
                    receipt_file=root_path / "receipt.json",
                    backend=backend,
                    pi_runner=mock.Mock(),
                )

        backend.activate.assert_not_called()
        backend.restore.assert_not_called()
        backend.verify_restored.assert_not_called()

    def test_verified_restoration_cancels_timer_then_releases_remote_mutex_last(self):
        profile = nuc_ondemand.PROFILES["qwen35-27b-review"]
        events = []
        backend = mock.Mock()
        backend.preflight.return_value = {"restoration_ready": True}
        backend.acquire.side_effect = lambda value: events.append("acquire")
        backend.activate.side_effect = lambda value: events.append("activate")
        backend.identity.return_value = {
            "model": profile.expected_model,
            "model_path": profile.model_path,
            "model_sha256": profile.model_sha256,
            "runtime_path": profile.runtime_path,
            "runtime_sha256": profile.runtime_sha256,
            "context_window": profile.context_window,
        }
        backend.restore.side_effect = lambda value: events.append("restore")
        backend.verify_restored.side_effect = lambda value: (
            events.append("verify") or {"restored": True}
        )
        backend.cancel_auto_restore.side_effect = lambda value: events.append("cancel")
        backend.release.side_effect = lambda value: events.append("release")

        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            prompt = root_path / "prompt.txt"
            prompt.write_text("Review this.", encoding="utf-8")
            result = nuc_ondemand.run_workcell(
                profile,
                prompt=prompt,
                cwd=root_path,
                log_file=root_path / "run.log",
                receipt_file=root_path / "receipt.json",
                backend=backend,
                pi_runner=mock.Mock(return_value=(0, "Status: DONE")),
            )

        self.assertEqual(result, 0)
        self.assertEqual(
            events,
            ["acquire", "activate", "restore", "verify", "cancel", "release"],
        )

    def test_pi_failure_still_restores_and_receipt_records_failure(self):
        profile = nuc_ondemand.PROFILES["qwen36-35b-coding"]
        backend = mock.Mock()
        backend.preflight.return_value = {"restoration_ready": True}
        backend.identity.return_value = {
            "model": profile.expected_model,
            "model_path": profile.model_path,
            "model_sha256": profile.model_sha256,
            "runtime_path": profile.runtime_path,
            "runtime_sha256": profile.runtime_sha256,
            "context_window": profile.context_window,
        }
        backend.verify_restored.return_value = {
            "restored": True,
            "qwen27_model": nuc_ondemand.BASELINE_MODEL,
        }
        pi_runner = mock.Mock(return_value=(4, "provider failed"))

        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            prompt = root_path / "prompt.txt"
            prompt.write_text("Fix the bounded fixture.", encoding="utf-8")
            receipt = root_path / "receipt.json"
            result = nuc_ondemand.run_workcell(
                profile,
                prompt=prompt,
                cwd=root_path,
                log_file=root_path / "run.log",
                receipt_file=receipt,
                backend=backend,
                pi_runner=pi_runner,
            )

            self.assertEqual(result, 4)
            payload = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertEqual(payload["result"], "failed")
            self.assertTrue(payload["restoration"]["restored"])
            self.assertEqual(payload["identity"]["model"], profile.expected_model)
            self.assertNotIn("api_key", json.dumps(payload).lower())

        backend.restore.assert_called_once_with(profile)
        backend.verify_restored.assert_called_once_with(profile)

    def test_mid_run_thermal_trip_fails_receipt_after_verified_restore(self):
        profile = nuc_ondemand.PROFILES["qwen35-35b-general"]

        class ThermalTripBackend:
            def __init__(self):
                self.trip_reads = iter(("", "reason=limit tctl_millic=90000"))

            def preflight(self, value):
                return {"restoration_ready": True}

            def acquire(self, value):
                return None

            def activate(self, value):
                return None

            def identity(self, value):
                return {
                    "model": value.expected_model,
                    "model_path": value.model_path,
                    "model_sha256": value.model_sha256,
                    "runtime_path": value.runtime_path,
                    "runtime_sha256": value.runtime_sha256,
                    "context_window": value.context_window,
                }

            def api_key(self, value):
                return "local"

            def thermal_trip(self, value):
                return next(self.trip_reads)

            def restore(self, value):
                return None

            def verify_restored(self, value):
                return {"restored": True}

            def cancel_auto_restore(self, value):
                return None

            def release(self, value):
                return None

        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            prompt = root_path / "prompt.txt"
            prompt.write_text("Bounded task.", encoding="utf-8")
            receipt = root_path / "receipt.json"
            with self.assertRaisesRegex(nuc_ondemand.WorkcellError, "thermal"):
                nuc_ondemand.run_workcell(
                    profile,
                    prompt=prompt,
                    cwd=root_path,
                    log_file=root_path / "run.log",
                    receipt_file=receipt,
                    backend=ThermalTripBackend(),
                    pi_runner=mock.Mock(return_value=(0, "Status: DONE")),
                )

            payload = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertEqual(payload["result"], "failed")
            self.assertEqual(
                payload["thermal_trip"],
                "reason=limit tctl_millic=90000",
            )
            self.assertTrue(payload["restoration"]["restored"])

    def test_restoration_failure_overrides_success(self):
        profile = nuc_ondemand.PROFILES["qwen35-27b-review"]
        backend = mock.Mock()
        backend.preflight.return_value = {"restoration_ready": True}
        backend.identity.return_value = {
            "model": profile.expected_model,
            "model_path": profile.model_path,
            "model_sha256": profile.model_sha256,
            "runtime_path": profile.runtime_path,
            "runtime_sha256": profile.runtime_sha256,
            "context_window": profile.context_window,
        }
        backend.verify_restored.return_value = {"restored": False}

        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            prompt = root_path / "prompt.txt"
            prompt.write_text("Review this.", encoding="utf-8")
            result = nuc_ondemand.run_workcell(
                profile,
                prompt=prompt,
                cwd=root_path,
                log_file=root_path / "run.log",
                receipt_file=root_path / "receipt.json",
                backend=backend,
                pi_runner=mock.Mock(return_value=(0, "Status: DONE")),
            )

        self.assertEqual(result, 4)
        backend.cancel_auto_restore.assert_not_called()
        backend.release.assert_not_called()

    def test_auto_restore_cancelled_only_after_verified_restoration(self):
        profile = nuc_ondemand.PROFILES["qwen35-27b-review"]
        backend = mock.Mock()
        backend.preflight.return_value = {"restoration_ready": True}
        backend.identity.return_value = {
            "model": profile.expected_model,
            "model_path": profile.model_path,
            "model_sha256": profile.model_sha256,
            "runtime_path": profile.runtime_path,
            "runtime_sha256": profile.runtime_sha256,
            "context_window": profile.context_window,
        }
        backend.verify_restored.return_value = {"restored": True}

        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            prompt = root_path / "prompt.txt"
            prompt.write_text("Review this.", encoding="utf-8")
            result = nuc_ondemand.run_workcell(
                profile,
                prompt=prompt,
                cwd=root_path,
                log_file=root_path / "run.log",
                receipt_file=root_path / "receipt.json",
                backend=backend,
                pi_runner=mock.Mock(return_value=(0, "Status: DONE")),
            )

        self.assertEqual(result, 0)
        backend.cancel_auto_restore.assert_called_once_with(profile)


if __name__ == "__main__":
    unittest.main()
