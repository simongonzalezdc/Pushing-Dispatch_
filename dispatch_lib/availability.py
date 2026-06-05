"""Resolve which executors are actually reachable right now.

Reachability by provider family:
  - anthropic    -> Claude Code logged in
  - openai-codex -> ~/.codex/auth.json present
  - local        -> CLI present (ollama / lm-studio endpoint)
  - kimi-cli     -> Kimi CLI present + OAuth credential store present
  - everything else (API-key providers) -> key resolvable (presence only)

Results cached to availability.json with a TTL. Secret VALUES are never read
into the cache or logs — only booleans.
"""
import hashlib
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
    # Claude Code stores its login token in the macOS Keychain under the
    # service "Claude Code-credentials".
    return _keychain_has("Claude Code-credentials", None)


def _codex_ready() -> bool:
    return (Path.home() / ".codex" / "auth.json").exists()


def _kimi_cli_ready() -> bool:
    """Return true when the local Kimi CLI OAuth login is usable.

    The Kimi Code CLI uses an OAuth credential file, not a Moonshot API key.
    Treat a refresh token as sufficient because the CLI can refresh short-lived
    access tokens itself.
    """
    if not (shutil.which("kimi") or shutil.which("kimi-cli")):
        return False

    cred_path = Path(
        os.environ.get(
            "KIMI_CREDENTIALS_PATH",
            str(Path.home() / ".kimi" / "credentials" / "kimi-code.json"),
        )
    )
    if not cred_path.exists():
        return False

    try:
        data = json.loads(cred_path.read_text())
    except (json.JSONDecodeError, OSError):
        return False

    if data.get("refresh_token"):
        return True

    expires_at = data.get("expires_at")
    return bool(
        data.get("access_token")
        and isinstance(expires_at, (int, float))
        and expires_at > time.time()
    )


def _local_ready(provider: str) -> bool:
    if provider in ("ollama", "codex-oss"):
        return shutil.which("ollama") is not None
    if provider == "lm-studio":
        # Endpoint reachability is checked by health/smoke paths. Availability
        # here means the local NUC contract can be resolved without cloud keys.
        return bool(
            os.environ.get("LM_STUDIO_BASE_URL")
            or os.environ.get("LMSTUDIO_BASE_URL")
            or os.environ.get("FACTORY_SELF_HOSTED_INFERENCE_URL")
            or os.environ.get("LOCAL_BASE_URL")
            or os.environ.get("LOCAL_API_KEY")
            or os.environ.get("PIPELINE_LOCAL_LLM_API_KEY")
            or _keychain_has("pushing-dispatch", "local_api_key")
            or _keychain_has("pushing-dispatch", "pipeline_local_llm_api_key")
        )
    return False


def _codex_config_has(env_var) -> bool:
    """Mirror ce_load_api_key's codex-config fallback (presence only)."""
    if not env_var:
        return False
    cfg = Path.home() / ".codex" / "config.toml"
    if not cfg.exists():
        return False
    try:
        import tomllib
        with open(cfg, "rb") as f:
            data = tomllib.load(f)
    except Exception:
        return False
    if data.get("shell_environment_policy", {}).get("set", {}).get(env_var):
        return True
    for server in data.get("mcp_servers", {}).values():
        if server.get("env", {}).get(env_var):
            return True
    return False


def _key_present(env_var, account) -> bool:
    """Mirror ce_load_api_key lookup order (presence only)."""
    if env_var and os.environ.get(env_var):
        return True
    if account and _keychain_has("pushing-dispatch", account):
        return True
    if _codex_config_has(env_var):
        return True
    return False


def _executor_available(cfg: dict) -> bool:
    provider = cfg.get("provider", "")
    if provider == "anthropic":
        return _anthropic_ready()
    if provider == "openai-codex":
        return _codex_ready()
    if provider == "kimi-cli":
        return _kimi_cli_ready()
    if provider in ("ollama", "lm-studio", "codex-oss"):
        return _local_ready(provider)
    return _key_present(cfg.get("key_env"), cfg.get("key_account"))


def resolve(matrix: dict, use_cache: bool = True) -> dict:
    """Return {executor: {"available": bool, "provider": str}} for all executors."""
    matrix_hash = _matrix_fingerprint(matrix)
    if use_cache:
        cached = _read_cache(matrix_hash)
        # Use cache only if it covers every executor currently in the matrix.
        # A partial/stale cache (e.g. after the matrix gained executors) is
        # discarded and recomputed — self-healing against matrix drift.
        if cached is not None and set(matrix.get("executors", {})) <= set(cached):
            return cached
    out = {}
    for name, cfg in matrix.get("executors", {}).items():
        out[name] = {
            "available": _executor_available(cfg),
            "provider": cfg.get("provider", ""),
        }
    _write_cache(out, matrix_hash)
    return out


def available_set(matrix: dict, use_cache: bool = True) -> set:
    return {k for k, v in resolve(matrix, use_cache=use_cache).items() if v["available"]}


def _matrix_fingerprint(matrix: dict) -> str:
    """Fingerprint availability-relevant matrix fields to avoid stale cache."""
    rows = []
    for name, cfg in sorted(matrix.get("executors", {}).items()):
        rows.append({
            "name": name,
            "provider": cfg.get("provider"),
            "key_env": cfg.get("key_env"),
            "key_account": cfg.get("key_account"),
            "wrapper": cfg.get("wrapper"),
            "model_id": cfg.get("model_id"),
        })
    blob = json.dumps(rows, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _read_cache(matrix_hash: str):
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
    if blob.get("matrix_hash") != matrix_hash:
        return None
    return blob.get("executors")


def _write_cache(executors: dict, matrix_hash: str) -> None:
    path = availability_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    with open(tmp, "w") as f:
        json.dump(
            {"ts": time.time(), "matrix_hash": matrix_hash, "executors": executors},
            f,
            indent=2,
        )
    os.replace(tmp, path)
