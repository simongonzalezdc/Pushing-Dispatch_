#!/usr/bin/env python3
"""Run one non-interactive Kimi CLI prompt for the shell wrapper."""

from __future__ import annotations

import os
import subprocess
import sys


def main() -> int:
    prompt_path = os.environ["KIMI_PROMPT_FILE"]
    with open(prompt_path, encoding="utf-8") as f:
        prompt = f.read()

    cmd = [
        os.environ.get("KIMI_CLI_BIN", "kimi"),
        "--print",
        "--final-message-only",
        "--afk",
        "--output-format",
        "text",
        "--work-dir",
        os.environ["KIMI_CWD"],
        "--model",
        os.environ.get("KIMI_MODEL", "kimi-code/kimi-for-coding"),
    ]

    config_file = os.environ.get("KIMI_CLI_CONFIG_FILE")
    if config_file:
        cmd.extend(["--config-file", config_file])

    config_inline = os.environ.get("KIMI_CLI_CONFIG")
    if config_inline:
        cmd.extend(["--config", config_inline])

    if os.environ.get("KIMI_READ_ONLY") == "1":
        cmd.append("--plan")

    cmd.extend(["--prompt", prompt])
    timeout = int(os.environ.get("KIMI_CLI_TIMEOUT_SECONDS", "600"))

    try:
        proc = subprocess.run(
            cmd,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        if exc.stdout:
            print(exc.stdout, end="")
        if exc.stderr:
            print(exc.stderr, end="", file=sys.stderr)
        print(f"Kimi CLI timed out after {timeout}s", file=sys.stderr)
        return 124

    if proc.stdout:
        print(proc.stdout, end="")
    if proc.stderr:
        print(proc.stderr, end="", file=sys.stderr)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
