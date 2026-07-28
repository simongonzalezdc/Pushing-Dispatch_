"""Fail-closed, reversible NUCBox model residency for bounded local workcells."""

from __future__ import annotations

import argparse
import base64
import fcntl
import json
import os
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence


HOST = "100.113.174.74"
BASELINE_MODEL = "unsloth/Qwen3.6-27B-MTP-GGUF"
BASELINE_URL = "http://127.0.0.1:8892"
IDENTITY_READY_TIMEOUT_SECONDS = 420
MAX_PREFLIGHT_TCTL_MILLIC = 85000
MAX_RUNTIME_TCTL_MILLIC = 90000
THERMAL_GUARD_PATH = "/home/simon/unsloth-ops/pushing-dispatch-thermal-guard.sh"
GPU_PERFORMANCE_LEVEL_PATH = (
    "/sys/class/drm/card1/device/power_dpm_force_performance_level"
)
SAFE_GPU_PERFORMANCE_LEVEL = "low"
STUDIO_UNIT = "unsloth-studio.service"
STUDIO_PROXY_UNIT = "unsloth-openai-proxy.service"
REMOTE_MUTEX_UNIT = "pushing-dispatch-nuc-workcell-mutex.service"
TARGET_UNITS = (
    "llama-qwen35-35b.service",
    "llama-qwen35-27b.service",
    "qwen36-moe-llama.service",
    "llama-27b.service",
    "llama-mtp.service",
)
DONE_RE = re.compile(r"(?m)^Status:\s*DONE(?:_WITH_CONCERNS)?\s*$")
CHARS_PER_TOKEN_ESTIMATE = 3
PI_INPUT_OVERHEAD_TOKENS = {
    # Measured 2026-07-23: the first slim-tool request was 2,993 tokens, while
    # its next tool-loop request reached 18,679. Round upward to cover bounded
    # tool-loop growth before NUC residency changes.
    "qwen36-35b-coding": 22000,
    # Measured 2026-07-23: a bounded read-only review tool loop reached 20,164
    # tokens. Use the same rounded reserve as coding.
    "qwen35-27b-review": 22000,
}


class WorkcellError(RuntimeError):
    pass


class WorkcellBusy(WorkcellError):
    pass


@dataclass(frozen=True)
class Profile:
    name: str
    family: str
    role: str
    service: str
    base_url: str
    expected_model: str
    model_path: str
    model_sha256: str
    runtime_path: str
    runtime_sha256: str
    context_window: int
    max_output_tokens: int
    tools: tuple[str, ...]
    api_key_file: str = ""


PROFILES = {
    "qwen35-35b-general": Profile(
        name="qwen35-35b-general",
        family="Qwen 3.5",
        role="general-builder",
        service="llama-qwen35-35b.service",
        base_url="http://100.113.174.74:8902/v1",
        expected_model="Qwen3.5-35B-A3B-Q4_K_M.gguf",
        model_path="/srv/external/models/gguf/Qwen3.5/Qwen3.5-35B-A3B-Q4_K_M.gguf",
        model_sha256="3b46d1066bc91cc2d613e3bc22ce691dd77e6f0d33c9060690d24ce6de494375",
        runtime_path="/srv/external/llama.cpp-b9611/build/bin/llama-server",
        runtime_sha256="a6a8f74f9730b09ada07cf467410fc41dbcdd894d6430a2d0cdad2d93e5ff944",
        context_window=32768,
        max_output_tokens=2048,
        tools=("read", "grep", "find", "ls"),
    ),
    "qwen35-27b-review": Profile(
        name="qwen35-27b-review",
        family="Qwen 3.5",
        role="general-reviewer",
        service="llama-qwen35-27b.service",
        base_url="http://100.113.174.74:8903/v1",
        expected_model="Qwen3.5-27B-Q4_K_M.gguf",
        model_path="/srv/external/models/gguf/Qwen3.5/Qwen3.5-27B-Q4_K_M.gguf",
        model_sha256="84b5f7f112156d63836a01a69dc3f11a6ba63b10a23b8ca7a7efaf52d5a2d806",
        runtime_path="/srv/external/llama.cpp-b9611/build/bin/llama-server",
        runtime_sha256="a6a8f74f9730b09ada07cf467410fc41dbcdd894d6430a2d0cdad2d93e5ff944",
        context_window=32768,
        max_output_tokens=512,
        tools=("read",),
    ),
    "qwen36-35b-coding": Profile(
        name="qwen36-35b-coding",
        family="Qwen 3.6",
        role="coding-builder",
        service="qwen36-moe-llama.service",
        base_url="http://100.113.174.74:1235/v1",
        expected_model="qwen3.6:35b",
        model_path="/srv/external/models/lmstudio/lmstudio-community/Qwen3.6-35B-A3B-GGUF/Qwen3.6-35B-A3B-Q4_K_M.gguf",
        model_sha256="4ac6a06bce551257267f49ad2226f8671a22519ccc1a4dde9d5b433d1f2a410d",
        runtime_path="/home/simon/runtimes/llama-cpp-rocm-b9253/extracted/llama-b9253/llama-server",
        runtime_sha256="eb0726d558964531e1f3687f388fde9bc63d9864debadfe050cd4c3decb98cda",
        context_window=32768,
        max_output_tokens=1024,
        tools=("read", "bash", "edit"),
        api_key_file="/srv/containers/nucbox/ai/llama-backend.key",
    ),
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, sort_keys=True, indent=2)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _residency_lock_path() -> Path:
    dispatch_root = Path(
        os.environ.get(
            "DISPATCH_ROOT",
            str(Path.home() / ".local" / "share" / "pushing-dispatch"),
        )
    )
    return dispatch_root / "state" / "nuc-ondemand.lock"


class RemoteBackend:
    """Fixed-command SSH backend. Model/profile values come only from PROFILES."""

    def __init__(self, host: str = HOST) -> None:
        self.host = host
        self.auto_restore_unit = f"pushing-dispatch-nuc-restore-{os.getpid()}"
        self.thermal_guard_unit = f"pushing-dispatch-nuc-thermal-guard-{os.getpid()}"

    def _ssh(self, script: str, *, timeout: int = 60) -> str:
        script = (
            "export XDG_RUNTIME_DIR=/run/user/$(id -u)\n"
            "export DBUS_SESSION_BUS_ADDRESS=unix:path=$XDG_RUNTIME_DIR/bus\n"
            + script
        )
        result = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", self.host, "bash", "-s"],
            input=script,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
        if result.returncode:
            raise WorkcellError(result.stderr.strip() or "NUCBox SSH command failed")
        return result.stdout

    def preflight(self, profile: Profile) -> dict:
        target_checks = "\n".join(
            "\n".join((
                f"printf 'target:{unit}='; sudo -n systemctl is-active {unit} || true",
                f"printf 'target_enabled:{unit}='; sudo -n systemctl is-enabled {unit} || true",
            ))
            for unit in TARGET_UNITS
        )
        script = f"""set -eu
printf 'baseline_active='; systemctl --user is-active unsloth-agent-qwen27.service
printf 'baseline_enabled='; systemctl --user is-enabled unsloth-agent-qwen27.service
printf 'watchdog_active='; systemctl --user is-active unsloth-agent-qwen27-watchdog.timer
printf 'watchdog_enabled='; systemctl --user is-enabled unsloth-agent-qwen27-watchdog.timer
printf 'studio_active='; systemctl --user is-active {STUDIO_UNIT} || true
printf 'studio_enabled='; systemctl --user is-enabled {STUDIO_UNIT} || true
printf 'studio_proxy_active='; systemctl --user is-active {STUDIO_PROXY_UNIT} || true
printf 'studio_proxy_enabled='; systemctl --user is-enabled {STUDIO_PROXY_UNIT} || true
printf 'mutex_active='; systemctl --user is-active {REMOTE_MUTEX_UNIT} || true
printf 'gpu_performance_level='; cat {GPU_PERFORMANCE_LEVEL_PATH}
tctl_path=''
for label in /sys/class/hwmon/hwmon*/temp*_label; do
  test -r "$label" || continue
  if test "$(cat "$label")" = Tctl; then
    tctl_path="${{label%_label}}_input"
    break
  fi
done
test -n "$tctl_path"
printf 'tctl_millic='; cat "$tctl_path"
{target_checks}
printf 'lease_b64='; ~/unsloth-ops/agent_maintenance.py status | base64 | tr -d '\n'
printf '\n'
printf 'catalog_b64='; curl -fsS {BASELINE_URL}/v1/models | base64 | tr -d '\n'
printf '\n'
"""
        values = _keyed_lines(self._ssh(script))
        catalog = _json_value(values, "catalog")
        models = _model_ids(catalog)
        try:
            tctl_millic = int(values.get("tctl_millic", ""))
        except ValueError:
            tctl_millic = MAX_PREFLIGHT_TCTL_MILLIC + 1
        ready = (
            values.get("baseline_active") == "active"
            and values.get("baseline_enabled") == "enabled"
            and values.get("watchdog_active") == "active"
            and values.get("watchdog_enabled") == "enabled"
            and values.get("studio_active") == "inactive"
            and values.get("studio_enabled") == "disabled"
            and values.get("studio_proxy_active") == "inactive"
            and values.get("studio_proxy_enabled") == "disabled"
            and values.get("mutex_active") == "inactive"
            and values.get("gpu_performance_level") == SAFE_GPU_PERFORMANCE_LEVEL
            and tctl_millic <= MAX_PREFLIGHT_TCTL_MILLIC
            and all(values.get(f"target:{unit}") == "inactive" for unit in TARGET_UNITS)
            and all(
                values.get(f"target_enabled:{unit}") == "disabled"
                for unit in TARGET_UNITS
            )
            and _json_value(values, "lease").get("status") == "inactive"
            and models == {BASELINE_MODEL}
        )
        if not ready:
            raise WorkcellError("NUCBox preflight cannot prove the restorable baseline")
        return {
            "restoration_ready": True,
            "baseline_model": BASELINE_MODEL,
            "studio_model": None,
        }

    def acquire(self, profile: Profile) -> None:
        target_checks = "\n".join(
            "\n".join((
                f"sudo -n systemctl is-active {unit} >/dev/null 2>&1 && conflict=1 || true",
                f"sudo -n systemctl is-enabled {unit} >/dev/null 2>&1 && conflict=1 || true",
            ))
            for unit in TARGET_UNITS
        )
        script = f"""set -eu
systemctl --user is-active {REMOTE_MUTEX_UNIT} >/dev/null 2>&1 && exit 23 || true
active_restore=$(systemctl --user list-units \
  'pushing-dispatch-nuc-restore-*' --state=active --no-legend --plain)
test -z "$active_restore" || exit 23
active_guard=$(systemctl --user list-units \
  'pushing-dispatch-nuc-thermal-guard-*' --state=active --no-legend --plain)
test -z "$active_guard" || exit 23
systemctl --user reset-failed {REMOTE_MUTEX_UNIT} >/dev/null 2>&1 || true
systemd-run --user --collect --unit={REMOTE_MUTEX_UNIT} \
  --property=RuntimeMaxSec=35m /usr/bin/sleep infinity >/dev/null
for attempt in $(seq 1 20); do
  systemctl --user is-active {REMOTE_MUTEX_UNIT} >/dev/null 2>&1 && break
  sleep 0.1
done
systemctl --user is-active {REMOTE_MUTEX_UNIT} >/dev/null
conflict=0
{target_checks}
lease=$(~/unsloth-ops/agent_maintenance.py status)
printf '%s' "$lease" | python3 -c \
  'import json,sys; raise SystemExit(0 if json.load(sys.stdin).get("status") == "inactive" else 1)' \
  || conflict=1
if test "$conflict" -ne 0; then
  systemctl --user stop {REMOTE_MUTEX_UNIT}
  exit 24
fi
"""
        try:
            self._ssh(script)
        except WorkcellError as error:
            raise WorkcellBusy("NUCBox remote residency mutex is unavailable") from error

    def activate(self, profile: Profile) -> None:
        units = " ".join(TARGET_UNITS)
        script = f"""set -eu
systemctl --user is-active {self.auto_restore_unit}.timer >/dev/null 2>&1 && exit 23 || true
systemd-run --user --collect --unit={self.auto_restore_unit} --on-active=25m /bin/bash -lc \
  'export XDG_RUNTIME_DIR=/run/user/$(id -u); export DBUS_SESSION_BUS_ADDRESS=unix:path=$XDG_RUNTIME_DIR/bus; sudo -n systemctl disable --now {units}; printf {SAFE_GPU_PERFORMANCE_LEVEL} | sudo -n tee {GPU_PERFORMANCE_LEVEL_PATH} >/dev/null; ~/unsloth-ops/agent_maintenance.py end || systemctl --user enable --now unsloth-agent-qwen27.service unsloth-agent-qwen27-watchdog.timer; systemctl --user disable --now {STUDIO_UNIT} {STUDIO_PROXY_UNIT}' >/dev/null
for attempt in $(seq 1 20); do
  systemctl --user is-active {self.auto_restore_unit}.timer >/dev/null 2>&1 && break
  sleep 0.1
done
systemctl --user is-active {self.auto_restore_unit}.timer >/dev/null
systemctl --user disable --now {STUDIO_UNIT} {STUDIO_PROXY_UNIT}
~/unsloth-ops/agent_maintenance.py begin --minutes 30 --reason pushing-dispatch-{profile.name} >/dev/null
thermal_marker="$XDG_RUNTIME_DIR/{self.thermal_guard_unit}.trip"
rm -f "$thermal_marker"
systemd-run --user --collect --unit={self.thermal_guard_unit} \
  --property=RuntimeMaxSec=35m {THERMAL_GUARD_PATH} \
  {MAX_RUNTIME_TCTL_MILLIC} "$thermal_marker" >/dev/null
for attempt in $(seq 1 20); do
  systemctl --user is-active {self.thermal_guard_unit} >/dev/null 2>&1 && break
  sleep 0.1
done
systemctl --user is-active {self.thermal_guard_unit} >/dev/null
printf {SAFE_GPU_PERFORMANCE_LEVEL} | sudo -n tee {GPU_PERFORMANCE_LEVEL_PATH} >/dev/null
test "$(cat {GPU_PERFORMANCE_LEVEL_PATH})" = {SAFE_GPU_PERFORMANCE_LEVEL}
sudo -n systemctl start {profile.service}
if ! systemctl --user is-active {self.thermal_guard_unit} >/dev/null 2>&1; then
  sudo -n systemctl disable --now {profile.service}
  exit 25
fi
"""
        self._ssh(script)

    def identity(self, profile: Profile) -> dict:
        port_url = profile.base_url.removesuffix("/v1").replace(HOST, "127.0.0.1")
        auth_header = ""
        if profile.api_key_file:
            auth_header = (
                f'-H "Authorization: Bearer $(sudo -n cat {profile.api_key_file})" '
            )
        catalog = None
        deadline = time.monotonic() + IDENTITY_READY_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            script = f"""set -eu
curl -fsS {port_url}/health >/dev/null
curl -fsS {auth_header}{port_url}/v1/models
"""
            try:
                output = self._ssh(script, timeout=20)
            except WorkcellError:
                time.sleep(3)
                continue
            try:
                catalog = json.loads(output)
            except json.JSONDecodeError:
                time.sleep(3)
                continue
            if _model_ids(catalog) != {profile.expected_model}:
                raise WorkcellError("target model identity mismatch")
            if _model_context(catalog, profile.expected_model) != profile.context_window:
                raise WorkcellError("target context window mismatch")
            break
        if catalog is None:
            raise WorkcellError("target endpoint did not become ready before the identity deadline")

        process_output = self._ssh(
            f"""set -eu
pid=$(sudo -n systemctl show {profile.service} --property=MainPID --value)
test "$pid" -gt 0
runtime_path=$(sudo -n readlink -f "/proc/$pid/exe")
cmdline=$(sudo -n sh -c "tr '\\0' '\\n' </proc/$pid/cmdline")
model_path=$(printf '%s\n' "$cmdline" | awk \
  'take {{ print; exit }} $0 == "-m" || $0 == "--model" {{ take=1; next }} \
   /^--model=/ {{ sub(/^--model=/, ""); print; exit }}')
test -n "$runtime_path"
test -n "$model_path"
printf 'runtime_path=%s\n' "$runtime_path"
printf 'model_path=%s\n' "$model_path"
printf 'runtime_sha256='; sha256sum "$runtime_path" | awk '{{print $1}}'
printf 'model_sha256='; sha256sum "$model_path" | awk '{{print $1}}'
""",
            timeout=300,
        )
        values = _keyed_lines(process_output)
        identity = {
            "model": next(iter(_model_ids(catalog)), ""),
            "model_path": values.get("model_path", ""),
            "model_sha256": values.get("model_sha256", ""),
            "runtime_path": values.get("runtime_path", ""),
            "runtime_sha256": values.get("runtime_sha256", ""),
            "context_window": _model_context(catalog, profile.expected_model),
        }
        _require_identity(profile, identity)
        return identity

    def api_key(self, profile: Profile) -> str:
        if not profile.api_key_file:
            return "local-nucbox"
        return self._ssh(f"set -eu\nsudo -n cat {profile.api_key_file}\n").strip()

    def thermal_trip(self, profile: Profile) -> str:
        return self._ssh(
            f"""set -eu
marker="$XDG_RUNTIME_DIR/{self.thermal_guard_unit}.trip"
test ! -s "$marker" || cat "$marker"
"""
        ).strip()

    def restore(self, profile: Profile) -> None:
        units = " ".join(TARGET_UNITS)
        self._ssh(
            f"""set +e
sudo -n systemctl disable --now {units}
stop_rc=$?
reset_rc=0
for unit in {units}; do
  if sudo -n systemctl is-failed "$unit" >/dev/null 2>&1; then
    sudo -n systemctl reset-failed "$unit" || reset_rc=$?
  fi
done
printf {SAFE_GPU_PERFORMANCE_LEVEL} | sudo -n tee {GPU_PERFORMANCE_LEVEL_PATH} >/dev/null
gpu_rc=$?
~/unsloth-ops/agent_maintenance.py end || systemctl --user enable --now unsloth-agent-qwen27.service unsloth-agent-qwen27-watchdog.timer
end_rc=$?
systemctl --user disable --now {STUDIO_UNIT} {STUDIO_PROXY_UNIT}
studio_rc=$?
test "$stop_rc" -eq 0 -a "$reset_rc" -eq 0 -a "$gpu_rc" -eq 0 -a "$end_rc" -eq 0 -a "$studio_rc" -eq 0
""",
            timeout=240,
        )

    def verify_restored(self, profile: Profile) -> dict:
        units = " ".join(TARGET_UNITS)
        script = f"""set -eu
printf 'baseline_active='; systemctl --user is-active unsloth-agent-qwen27.service
printf 'baseline_enabled='; systemctl --user is-enabled unsloth-agent-qwen27.service
printf 'watchdog_active='; systemctl --user is-active unsloth-agent-qwen27-watchdog.timer
printf 'watchdog_enabled='; systemctl --user is-enabled unsloth-agent-qwen27-watchdog.timer
printf 'studio_active='; systemctl --user is-active {STUDIO_UNIT} || true
printf 'studio_enabled='; systemctl --user is-enabled {STUDIO_UNIT} || true
printf 'studio_proxy_active='; systemctl --user is-active {STUDIO_PROXY_UNIT} || true
printf 'studio_proxy_enabled='; systemctl --user is-enabled {STUDIO_PROXY_UNIT} || true
printf 'mutex_active='; systemctl --user is-active {REMOTE_MUTEX_UNIT}
printf 'gpu_performance_level='; cat {GPU_PERFORMANCE_LEVEL_PATH}
for unit in {units}; do
  printf "target:$unit="; sudo -n systemctl is-active "$unit" || true
  printf "target_enabled:$unit="; sudo -n systemctl is-enabled "$unit" || true
done
printf 'lease_b64='; ~/unsloth-ops/agent_maintenance.py status | base64 | tr -d '\n'
printf '\n'
catalog=''
for attempt in $(seq 1 60); do
  candidate=$(curl -fsS {BASELINE_URL}/v1/models 2>/dev/null || true)
  if test -n "$candidate" && printf '%s' "$candidate" | grep -Fq '"{BASELINE_MODEL}"'; then
    catalog=$candidate
    break
  fi
  sleep 3
done
test -n "$catalog"
printf 'catalog_b64='; printf '%s' "$catalog" | base64 | tr -d '\n'
printf '\n'
"""
        values = _keyed_lines(self._ssh(script, timeout=240))
        catalog = _json_value(values, "catalog")
        targets_inactive = all(
            values.get(f"target:{unit}") == "inactive" for unit in TARGET_UNITS
        )
        targets_disabled = all(
            values.get(f"target_enabled:{unit}") == "disabled"
            for unit in TARGET_UNITS
        )
        restored = (
            values.get("baseline_active") == "active"
            and values.get("baseline_enabled") == "enabled"
            and values.get("watchdog_active") == "active"
            and values.get("watchdog_enabled") == "enabled"
            and values.get("studio_active") == "inactive"
            and values.get("studio_enabled") == "disabled"
            and values.get("studio_proxy_active") == "inactive"
            and values.get("studio_proxy_enabled") == "disabled"
            and values.get("mutex_active") == "active"
            and values.get("gpu_performance_level") == SAFE_GPU_PERFORMANCE_LEVEL
            and targets_inactive
            and targets_disabled
            and _json_value(values, "lease").get("status") == "inactive"
            and _model_ids(catalog) == {BASELINE_MODEL}
        )
        return {"restored": restored, "qwen27_model": next(iter(_model_ids(catalog)), "")}

    def cancel_auto_restore(self, profile: Profile) -> None:
        self._ssh(
            f"""set +e
systemctl --user stop {self.auto_restore_unit}.timer {self.auto_restore_unit}.service {self.thermal_guard_unit}.service
systemctl --user reset-failed {self.auto_restore_unit}.timer {self.auto_restore_unit}.service {self.thermal_guard_unit}.service
rm -f "$XDG_RUNTIME_DIR/{self.thermal_guard_unit}.trip"
exit 0
"""
        )

    def release(self, profile: Profile) -> None:
        self._ssh(
            f"""set -eu
systemctl --user stop {REMOTE_MUTEX_UNIT}
systemctl --user reset-failed {REMOTE_MUTEX_UNIT} >/dev/null 2>&1 || true
test "$(systemctl --user is-active {REMOTE_MUTEX_UNIT} || true)" = inactive
"""
        )


def _keyed_lines(output: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in output.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return values


def _json_value(values: dict[str, str], key: str) -> dict:
    encoded = values.get(f"{key}_b64")
    if encoded is not None:
        try:
            raw = base64.b64decode(encoded, validate=True).decode("utf-8")
            payload = json.loads(raw)
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise WorkcellError(f"invalid encoded {key} payload") from error
    else:
        try:
            payload = json.loads(values.get(key, "{}"))
        except json.JSONDecodeError as error:
            raise WorkcellError(f"invalid {key} payload") from error
    if not isinstance(payload, dict):
        raise WorkcellError(f"invalid {key} payload")
    return payload


def _model_ids(payload: dict) -> set[str]:
    rows = payload.get("data", payload.get("models", []))
    return {
        str(item.get("id") or item.get("model") or item.get("name"))
        for item in rows
        if isinstance(item, dict) and (item.get("id") or item.get("model") or item.get("name"))
    }


def _model_context(payload: dict, expected_model: str) -> int | None:
    rows = payload.get("data", payload.get("models", []))
    contexts = {
        item.get("meta", {}).get("n_ctx")
        for item in rows
        if isinstance(item, dict)
        and (item.get("id") or item.get("model") or item.get("name")) == expected_model
        and isinstance(item.get("meta"), dict)
    }
    if len(contexts) != 1:
        return None
    context = next(iter(contexts))
    return context if isinstance(context, int) and not isinstance(context, bool) else None


def _require_identity(profile: Profile, identity: dict) -> None:
    if identity.get("model") != profile.expected_model:
        raise WorkcellError("target model identity mismatch")
    if identity.get("model_path") != profile.model_path:
        raise WorkcellError("target model process path mismatch")
    if identity.get("model_sha256") != profile.model_sha256:
        raise WorkcellError("target checkpoint digest mismatch")
    if identity.get("runtime_path") != profile.runtime_path:
        raise WorkcellError("target runtime process path mismatch")
    if identity.get("runtime_sha256") != profile.runtime_sha256:
        raise WorkcellError("target runtime digest mismatch")
    if identity.get("context_window") != profile.context_window:
        raise WorkcellError("target context window mismatch")


def _require_request_capacity(profile: Profile, prompt: Path) -> dict:
    prompt_text = prompt.read_text(encoding="utf-8")
    prompt_tokens = (
        len(prompt_text.encode("utf-8")) + CHARS_PER_TOKEN_ESTIMATE - 1
    ) // CHARS_PER_TOKEN_ESTIMATE
    overhead_tokens = PI_INPUT_OVERHEAD_TOKENS.get(profile.name, 0)
    estimated_tokens = overhead_tokens + prompt_tokens + profile.max_output_tokens
    if overhead_tokens and estimated_tokens > profile.context_window:
        raise WorkcellError(
            f"estimated request {estimated_tokens} tokens exceeds "
            f"{profile.context_window}-token context"
        )
    return {
        "estimated_request_tokens": estimated_tokens,
        "prompt_tokens": prompt_tokens,
        "fixed_overhead_tokens": overhead_tokens,
        "reserved_output_tokens": profile.max_output_tokens,
        "context_window": profile.context_window,
    }


def default_pi_runner(profile: Profile, prompt: Path, cwd: Path, log_file: Path,
                      api_key: str) -> tuple[int, str]:
    with tempfile.TemporaryDirectory(prefix="dispatch-nuc-pi-") as agent_root:
        agent_dir = Path(agent_root)
        _write_json(agent_dir / "auth.json", {})
        _write_json(agent_dir / "models.json", {
            "providers": {
                profile.name: {
                    "baseUrl": profile.base_url,
                    "api": "openai-completions",
                    "apiKey": api_key,
                    "compat": {
                        "supportsDeveloperRole": False,
                        "supportsReasoningEffort": False,
                        "supportsUsageInStreaming": False,
                        "maxTokensField": "max_tokens",
                        "thinkingFormat": "qwen",
                    },
                    "models": [{
                        "id": profile.expected_model,
                        "name": profile.name,
                        "reasoning": True,
                        "input": ["text"],
                        "contextWindow": profile.context_window,
                        "maxTokens": profile.max_output_tokens,
                        "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0},
                    }],
                }
            }
        })
        command = [
            "pi",
            "--provider", profile.name,
            "--model", profile.expected_model,
            "--thinking", "off",
            "--no-session",
            "--no-extensions",
            "--no-skills",
            "--no-prompt-templates",
            "--no-context-files",
            "--tools", ",".join(profile.tools),
            "--append-system-prompt",
            (
                f"You are the bounded {profile.role} pass. Use only the admitted tools. "
                "Stop after the requested verification. End with Status: DONE, "
                "Status: NEEDS_GUIDANCE, or Status: BLOCKED."
            ),
            "--print", prompt.read_text(encoding="utf-8"),
        ]
        env = os.environ.copy()
        env["PI_CODING_AGENT_DIR"] = str(agent_dir)
        try:
            completed = subprocess.run(
                command,
                cwd=cwd,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=600,
            )
            output = completed.stdout or ""
            code = completed.returncode
        except subprocess.TimeoutExpired as error:
            output = error.stdout or ""
            code = 4
        log_file.parent.mkdir(parents=True, exist_ok=True)
        log_file.write_text(output, encoding="utf-8")
        if code == 0 and not DONE_RE.search(output):
            code = 4
        return code, output


def run_workcell(profile: Profile, *, prompt: Path, cwd: Path, log_file: Path,
                 receipt_file: Path, backend: RemoteBackend | object | None = None,
                 pi_runner: Callable = default_pi_runner) -> int:
    backend = backend or RemoteBackend()
    started = _utc_now()
    preflight: dict = {}
    identity: dict = {}
    restoration: dict = {"restored": False}
    result_code = 4
    output = ""
    activated = False
    error: Exception | None = None
    thermal_trip = ""

    try:
        preflight["request_capacity"] = _require_request_capacity(profile, prompt)
        preflight = backend.preflight(profile)
        preflight["request_capacity"] = _require_request_capacity(profile, prompt)
        backend.acquire(profile)
        # Activation is a multi-command remote transaction. Once it begins,
        # an SSH loss can hide a partially applied maintenance lease or target
        # start, so restoration is required even if activate() raises.
        activated = True
        backend.activate(profile)
        identity = backend.identity(profile)
        _require_identity(profile, identity)
        if hasattr(type(backend), "thermal_trip"):
            thermal_trip = backend.thermal_trip(profile)
            if thermal_trip:
                raise WorkcellError(f"thermal guard tripped: {thermal_trip}")
        api_key = backend.api_key(profile) if hasattr(backend, "api_key") else ""
        result_code, output = pi_runner(profile, prompt, cwd, log_file, api_key)
    except Exception as caught:
        error = caught
    finally:
        if activated:
            if hasattr(type(backend), "thermal_trip"):
                try:
                    observed_trip = backend.thermal_trip(profile)
                    thermal_trip = observed_trip or thermal_trip
                    if thermal_trip and error is None:
                        error = WorkcellError(
                            f"thermal guard tripped: {thermal_trip}"
                        )
                except Exception as trip_error:
                    if error is None:
                        error = trip_error
            try:
                backend.restore(profile)
                restoration = backend.verify_restored(profile)
                if restoration.get("restored") is True:
                    backend.cancel_auto_restore(profile)
                    backend.release(profile)
            except Exception as restore_error:
                restoration = {"restored": False, "error": str(restore_error)}

    if restoration.get("restored") is not True:
        result_code = 4
    elif error is not None:
        result_code = 4

    _write_json(receipt_file, {
        "schema_version": 1,
        "profile": profile.name,
        "family": profile.family,
        "role": profile.role,
        "started_at_utc": started,
        "finished_at_utc": _utc_now(),
        "preflight": preflight,
        "identity": identity,
        "result": "passed" if result_code == 0 else "failed",
        "failure_reason": type(error).__name__ if error is not None else None,
        "failure_detail": str(error) if error is not None else None,
        "thermal_trip": thermal_trip or None,
        "worker_output_status": "done" if DONE_RE.search(output) else "not_done",
        "restoration": restoration,
        "production_routing_changed": False,
        "metered_cost_usd": None,
    })

    if error is not None:
        if isinstance(error, WorkcellError):
            raise error
        raise WorkcellError(str(error)) from error
    return result_code


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, choices=sorted(PROFILES))
    parser.add_argument("--prompt-file", required=True, type=Path)
    parser.add_argument("--cwd", required=True, type=Path)
    parser.add_argument("--log-file", required=True, type=Path)
    parser.add_argument("--receipt-file", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    profile = PROFILES[args.profile]
    if args.dry_run:
        print(json.dumps({
            "profile": profile.name,
            "family": profile.family,
            "role": profile.role,
            "model": profile.expected_model,
            "model_sha256": profile.model_sha256,
            "runtime_sha256": profile.runtime_sha256,
            "tools": profile.tools,
            "production_routing_changed": False,
        }, sort_keys=True))
        return 0
    lock_path = _residency_lock_path()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.touch(mode=0o600, exist_ok=True)
    with lock_path.open("r+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise SystemExit("another NUCBox on-demand workcell owns the residency lock") from error
        try:
            return run_workcell(
                profile,
                prompt=args.prompt_file,
                cwd=args.cwd,
                log_file=args.log_file,
                receipt_file=args.receipt_file,
            )
        except WorkcellError as error:
            print(str(error), file=os.sys.stderr)
            return 4


if __name__ == "__main__":
    raise SystemExit(main())
