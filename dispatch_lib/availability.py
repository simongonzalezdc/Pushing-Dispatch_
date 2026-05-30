"""Resolve which executors are actually reachable right now.

Reachability by provider family:
  - anthropic    -> Claude Code logged in
  - openai-codex -> ~/.codex/auth.json present
  - local        -> CLI present (ollama / lm-studio endpoint)
  - everything else (API-key providers) -> key resolvable (presence only)

Results cached to availability.json with a TTL. Secret VALUES are never read
into the cache or logs — only booleans.
"""
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from .path_conventions import availability_path

CACHE_TTL_SECONDS = 300


def _keychain_has(service: str, account) -> bool:
    if not shutil.which("security"):
        return False
    cmd = ["security", "find-generic-password", "-s", service]
    if account:
        cmd += ["-a", account]
    return subprocess.run(cmd, capture_output=True).returncode == 0


def _anthropic_ready() -> bool:
    # Claude Code stores creds in a credentials file or Keychain depending on
    # platform; treat presence of any as logged in.
    if (Path.home() / ".claude" / ".credentials.json").exists():
        return True
    if os.environ.get("ANTHROPIC_API_KEY"):
        return True
    return _keychain_has("Claude Code", None) or _keychain_has("claude.ai", None)


def _codex_ready() -> bool:
    return (Path.home() / ".codex" / "auth.json").exists()


def _local_ready(provider: str) -> bool:
    if provider in ("ollama", "codex-oss"):
        return shutil.which("ollama") is not None
    if provider == "lm-studio":
        # Endpoint reachability is checked lazily; presence of base url env or
        # OPENAI_API_KEY is the cheap proxy here.
        return bool(os.environ.get("LM_STUDIO_BASE_URL") or os.environ.get("OPENAI_API_KEY"))
    return False


def _key_present(env_var, account) -> bool:
    """Mirror ce_load_api_key lookup order (presence only)."""
    if env_var and os.environ.get(env_var):
        return True
    if account and _keychain_has("pushing-dispatch", account):
        return True
    return False


def _executor_available(cfg: dict) -> bool:
    provider = cfg.get("provider", "")
    if provider == "anthropic":
        return _anthropic_ready()
    if provider == "openai-codex":
        return _codex_ready()
    if provider in ("ollama", "lm-studio", "codex-oss"):
        return _local_ready(provider)
    return _key_present(cfg.get("key_env"), cfg.get("key_account"))


def resolve(matrix: dict, use_cache: bool = True) -> dict:
    """Return {executor: {"available": bool, "provider": str}} for all executors."""
    if use_cache:
        cached = _read_cache()
        if cached is not None:
            return cached
    out = {}
    for name, cfg in matrix.get("executors", {}).items():
        out[name] = {
            "available": _executor_available(cfg),
            "provider": cfg.get("provider", ""),
        }
    _write_cache(out)
    return out


def available_set(matrix: dict, use_cache: bool = True) -> set:
    return {k for k, v in resolve(matrix, use_cache=use_cache).items() if v["available"]}


def _read_cache():
    path = availability_path()
    if not path.exists():
        return None
    try:
        with open(path) as f:
            blob = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
    if time.time() - blob.get("ts", 0) > CACHE_TTL_SECONDS:
        return None
    return blob.get("executors")


def _write_cache(executors: dict) -> None:
    path = availability_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    with open(tmp, "w") as f:
        json.dump({"ts": time.time(), "executors": executors}, f, indent=2)
    os.replace(tmp, path)
