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
import urllib.error
import urllib.request
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
    # Per-account dispatch homes (~/.codex-dispatch/<account>/auth.json) are
    # the preferred auth source; the shared ~/.codex/auth.json remains valid
    # for setups that have not migrated.
    if any((Path.home() / ".codex-dispatch").glob("*/auth.json")):
        return True
    return (Path.home() / ".codex" / "auth.json").exists()


def _grok_ready() -> bool:
    """Return whether the official Grok CLI has a usable auth source."""
    if shutil.which("grok") is None:
        return False
    if os.environ.get("XAI_API_KEY"):
        return True
    # OAuth login stores its refreshable session here. Presence is sufficient;
    # the CLI owns token validation and refresh without exposing secret values.
    return (Path.home() / ".grok" / "auth.json").exists()


def _health_url_ready(cfg: dict) -> bool:
    health_url = cfg.get("health_url")
    if not health_url:
        return True
    try:
        with urllib.request.urlopen(health_url, timeout=2) as response:
            if not 200 <= response.status < 300:
                return False
            if not health_url.rstrip("/").endswith("/models"):
                return True
            expected_model = str(cfg.get("model_id", "")).strip()
            if not expected_model:
                return False
            payload = json.load(response)
            model_ids = {
                item.get("id") or item.get("model") or item.get("name")
                for item in payload.get("data", payload.get("models", []))
                if isinstance(item, dict)
            }
            return any(
                actual == expected_model or actual == f"{expected_model}:latest"
                for actual in model_ids
            )
    except (json.JSONDecodeError, TypeError, urllib.error.URLError, TimeoutError, OSError):
        return False


def _local_ready(provider: str, cfg: dict) -> bool:
    if cfg.get("on_demand") is True:
        activation_url = str(cfg.get("activation_health_url", "")).strip()
        activation_model = str(cfg.get("activation_model_id", "")).strip()
        if not activation_url or not activation_model:
            return False
        if not _health_url_ready({
            "health_url": activation_url,
            "model_id": activation_model,
        }):
            return False
    elif not _health_url_ready(cfg):
        return False
    validator_url = str(cfg.get("validator_health_url", "")).strip()
    validator_model = str(cfg.get("validator_model_id", "")).strip()
    if bool(validator_url) != bool(validator_model):
        return False
    if validator_url and not _health_url_ready({
        "health_url": validator_url,
        "model_id": validator_model,
    }):
        return False
    if provider in ("ollama", "unsloth-openai"):
        # A remote fleet executor is defined by its endpoint, not by whether the
        # caller happens to have an Ollama CLI installed.
        if cfg.get("health_url"):
            return True
        return shutil.which("ollama") is not None
    if provider == "lm-studio":
        # Endpoint reachability is checked by health/smoke paths. Availability
        # here means the local NUC contract can be resolved without cloud keys.
        return bool(
            os.environ.get("LM_STUDIO_BASE_URL")
            or os.environ.get("LMSTUDIO_BASE_URL")
            or os.environ.get("NUCBOX_OLLAMA_OPENAI_BASE_URL")
            or os.environ.get("NUCBOX_GEMMA_BASE_URL")
            or os.environ.get("OLLAMA_OPENAI_BASE_URL")
            or os.environ.get("FACTORY_SELF_HOSTED_INFERENCE_URL")
            or os.environ.get("LOCAL_BASE_URL")
            or os.environ.get("LOCAL_API_KEY")
            or os.environ.get("PIPELINE_LOCAL_LLM_API_KEY")
            or _keychain_has("pushing-dispatch", "local_api_key")
            or _keychain_has("pushing-dispatch", "pipeline_local_llm_api_key")
        )
    return False


def _ollama_cloud_model_ready(cfg: dict) -> bool:
    """Fail closed unless the configured Ollama Cloud model is live."""
    if not _key_present(cfg.get("key_env"), cfg.get("key_account")):
        return False
    model = str(cfg.get("model_id", "")).strip()
    if not model:
        return False
    request = urllib.request.Request(
        f"https://ollama.com/v1/models/{model}",
        headers={"Authorization": f"Bearer {_load_ollama_cloud_key(cfg)}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return 200 <= response.status < 300
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def _load_ollama_cloud_key(cfg: dict) -> str:
    """Load only the Ollama credential; never inspect Kimi credentials."""
    env_var = cfg.get("key_env") or "OLLAMA_API_KEY"
    if os.environ.get(env_var):
        return os.environ[env_var]
    if shutil.which("security") and cfg.get("key_account"):
        result = subprocess.run(
            ["security", "find-generic-password", "-s", "pushing-dispatch", "-a", cfg["key_account"], "-w"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    return ""


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


def _zai_ready() -> bool:
    """GLM runs through ZCode; the lane is available only where a zcode
    binary can actually be resolved (CLI on PATH or the ZCode.app bundle)."""
    if shutil.which("zcode") is not None:
        return True
    return (Path.home() / "Applications/ZCode.app/Contents/Resources/glm/zcode.cjs").exists() or \
        Path("/Applications/ZCode.app/Contents/Resources/glm/zcode.cjs").exists()


def _executor_available(cfg: dict) -> bool:
    if cfg.get("disabled") is True:
        return False
    provider = cfg.get("provider", "")
    if provider == "zai":
        return _zai_ready()
    if provider == "deepseek-dsh":
        return shutil.which("dsh") is not None
    if provider == "agy":
        return shutil.which("agy") is not None
    if provider == "kilo-cli":
        return shutil.which("kilo") is not None
    if provider == "kimi-cli":
        return shutil.which("kimi") is not None
    if provider == "gjc":
        return shutil.which("gjc") is not None
    if provider == "grok-cli":
        return _grok_ready()
    if provider == "anthropic":
        return _anthropic_ready()
    if provider == "openai-codex":
        return _codex_ready()
    if provider == "ollama-cloud":
        return _ollama_cloud_model_ready(cfg)
    if provider in ("ollama", "lm-studio", "unsloth-openai"):
        return _local_ready(provider, cfg)
    return _key_present(cfg.get("key_env"), cfg.get("key_account"))


def resolve(matrix: dict, use_cache: bool = True) -> dict:
    """Return {executor: {"available": bool, "provider": str}} for all executors."""
    if use_cache:
        cached = _read_cache()
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
