#!/usr/bin/env python3
"""Make Hermes's native provider layer match the canonical Dispatch boundary."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import shutil
import tempfile

import yaml


ZAI_BASE_URL = "https://api.z.ai/api/coding/paas/v4"


def canonicalize(config: dict) -> dict:
    model = dict(config.get("model") or {})
    model.update(
        provider="zai",
        default="glm-5.3",
        base_url=ZAI_BASE_URL,
        api_mode="chat_completions",
    )
    config["model"] = model

    existing = config.get("providers") or {}
    ollama = dict(existing.get("ollama-local") or {})
    ollama.setdefault("request_timeout_seconds", 300)
    ollama.setdefault("stale_timeout_seconds", 900)
    zai = dict(existing.get("zai") or {})
    zai.update(
        api_key="",
        api_mode="chat_completions",
        base_url=ZAI_BASE_URL,
        model="glm-5.3",
        reasoning_effort="high",
    )
    config["providers"] = {"ollama-local": ollama, "zai": zai}
    config["fallback_providers"] = []
    config["custom_providers"] = []

    delegation = dict(config.get("delegation") or {})
    delegation.update(
        provider="zai",
        model="glm-5.3",
        base_url=ZAI_BASE_URL,
        api_key="",
        api_mode="chat_completions",
        orchestrator_enabled=True,
    )
    config["delegation"] = delegation
    return config


def dump_config(path: Path, config: dict, mode: int) -> None:
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as handle:
        yaml.safe_dump(config, handle, sort_keys=False, allow_unicode=True)
        temporary = Path(handle.name)
    temporary.chmod(mode)
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path.home() / ".hermes" / "config.yaml")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    path = args.config.expanduser()
    original = yaml.safe_load(path.read_text()) or {}
    expected = canonicalize(dict(original))
    if args.check:
        if original != expected:
            print("Hermes routing configuration is not canonical")
            return 1
        print("Hermes routing configuration is canonical")
        return 0

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = path.with_name(f"{path.name}.pre-dispatch-{timestamp}")
    shutil.copy2(path, backup)
    dump_config(path, expected, 0o600)
    print(f"Updated {path}")
    print(f"Backup: {backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
