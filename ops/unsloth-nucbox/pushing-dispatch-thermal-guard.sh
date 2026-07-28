#!/usr/bin/env bash
set -euo pipefail

limit_millic=${1:?temperature limit in milli-Celsius is required}
marker_path=${2:-}
hwmon_root=${HWMON_ROOT:-/sys/class/hwmon}
sample_interval=${THERMAL_SAMPLE_INTERVAL_SECONDS:-2}
gpu_performance_level_path=${GPU_PERFORMANCE_LEVEL_PATH:-/sys/class/drm/card1/device/power_dpm_force_performance_level}
target_units=(
  llama-qwen35-35b.service
  llama-qwen35-27b.service
  qwen36-moe-llama.service
  llama-27b.service
  llama-mtp.service
)

restore_single_resident_baseline() {
  sudo -n systemctl disable --now "${target_units[@]}" || return 1
  for unit in "${target_units[@]}"; do
    test "$(sudo -n systemctl is-active "$unit" 2>/dev/null || true)" = inactive ||
      return 1
    test "$(sudo -n systemctl is-enabled "$unit" 2>/dev/null || true)" = disabled ||
      return 1
  done
  if test -e "$gpu_performance_level_path"; then
    printf low | sudo -n tee "$gpu_performance_level_path" >/dev/null ||
      return 1
    test "$(cat "$gpu_performance_level_path")" = low || return 1
  fi

  "$HOME/unsloth-ops/agent_maintenance.py" end ||
    systemctl --user enable --now \
      unsloth-agent-qwen27.service \
      unsloth-agent-qwen27-watchdog.timer ||
    return 1
  systemctl --user disable --now unsloth-studio.service unsloth-openai-proxy.service ||
    return 1
  test "$(systemctl --user is-active unsloth-agent-qwen27.service)" = active ||
    return 1
  test "$(systemctl --user is-active unsloth-agent-qwen27-watchdog.timer)" = active ||
    return 1
  test "$(systemctl --user is-active unsloth-studio.service 2>/dev/null || true)" = inactive ||
    return 1
  test "$(systemctl --user is-enabled unsloth-studio.service 2>/dev/null || true)" = disabled ||
    return 1
  test "$(systemctl --user is-active unsloth-openai-proxy.service 2>/dev/null || true)" = inactive ||
    return 1
  test "$(systemctl --user is-enabled unsloth-openai-proxy.service 2>/dev/null || true)" = disabled
}

restore_until_safe() {
  until restore_single_resident_baseline; do
    echo "thermal_guard=restore_failed retry_seconds=2" >&2
    sleep 2
  done
}

trip() {
  local reason=$1
  local exit_code=$2
  if test -n "$marker_path"; then
    printf '%s\n' "$reason" >"$marker_path"
  fi
  echo "thermal_guard=tripped $reason" >&2
  restore_until_safe
  exit "$exit_code"
}

on_signal() {
  trip "reason=signal" 143
}
trap on_signal TERM INT

while true; do
  tctl_millic=
  for label in "$hwmon_root"/hwmon*/temp*_label; do
    test -r "$label" || continue
    if test "$(cat "$label")" = Tctl; then
      tctl_millic=$(cat "${label%_label}_input" 2>/dev/null || true)
      break
    fi
  done

  if ! [[ "$tctl_millic" =~ ^[0-9]+$ ]]; then
    trip "reason=unreadable_tctl" 70
  fi
  if ! test "$tctl_millic" -lt "$limit_millic"; then
    trip "reason=limit tctl_millic=$tctl_millic limit_millic=$limit_millic" 75
  fi
  sleep "$sample_interval"
done
