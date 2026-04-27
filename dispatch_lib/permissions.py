"""
Nested dispatch permission checks.

The permissions matrix lives in dispatch_matrix.toml under
[nested_dispatch.permissions]. Each entry: parent.child = true|false.
Missing entries are treated as denied.

Hard rules (always enforced, cannot be overridden by matrix):
  - Self-dispatch denied (loop prevention)
  - Leaf executors cannot dispatch (haiku, minimax, ollama-local)
  - Metered -> high-cost-subscription dispatch denied (cost-asymmetric)
"""

from pathlib import Path

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None


# Executors that may never dispatch sub-workers
LEAF_EXECUTORS = {"haiku", "minimax", "ollama-local", "gemini"}

# Provider cost tiers: metered providers charge per-token (budget-capped),
# subscription providers have flat-rate access (unbounded per-call cost).
METERED_PROVIDERS = frozenset({"minimax", "moonshot", "deepseek", "ollama"})
SUBSCRIPTION_PROVIDERS = frozenset({"anthropic", "google"})

# High-cost subscription executors blocked from metered parents.
# Haiku is anthropic (subscription) but cheap/bounded -- explicitly allowed
# by the permissions table (kimi->haiku, deepseek->haiku). Only Opus and
# Sonnet represent the "unbounded subscription cost" concern.
HIGH_COST_SUBSCRIPTION = frozenset({"opus", "sonnet"})

# Executor -> provider mapping. Mirrors dispatch_matrix.toml for fast lookup
# without a full matrix parse in the hot path.
_EXECUTOR_PROVIDERS = {
    "opus":       "anthropic",
    "sonnet":     "anthropic",
    "haiku":      "anthropic",
    "minimax":    "minimax",
    "kimi":       "moonshot",
    "kimi-think": "moonshot",
    "deepseek":   "deepseek",
    "gemini":     "google",
    "ollama-local": "ollama",
}


def _is_metered(executor: str) -> bool:
    """True if the executor's provider uses metered (per-token) billing."""
    provider = _EXECUTOR_PROVIDERS.get(executor, "")
    return provider in METERED_PROVIDERS


def _is_subscription(executor: str) -> bool:
    """True if the executor's provider uses subscription (flat-rate) billing."""
    provider = _EXECUTOR_PROVIDERS.get(executor, "")
    return provider in SUBSCRIPTION_PROVIDERS


def check_nested_permission(
    parent_executor: str,
    child_executor: str,
    matrix_path: str = None,
) -> tuple[bool, str]:
    """Check if parent_executor is allowed to dispatch child_executor.

    Applies hard rules first (self-dispatch, leaf, cost-asymmetric),
    then consults the [nested_dispatch.permissions] matrix table.

    Returns: (allowed: bool, reason: str)
    """
    # Hard rule 1: self-dispatch always denied
    if parent_executor == child_executor:
        return False, (f"Self-dispatch denied: {parent_executor} cannot spawn "
                       f"{parent_executor} (loop risk)")

    # Hard rule 2: leaf executors cannot dispatch
    if parent_executor in LEAF_EXECUTORS:
        return False, (f"Leaf executor {parent_executor} cannot dispatch "
                       f"sub-workers (leaf tier: no nested dispatch allowed)")

    # Hard rule 3: metered -> high-cost-subscription cost-asymmetric block.
    # Blocks metered parents (kimi, deepseek, minimax) from spawning Opus or
    # Sonnet. Haiku is anthropic (subscription) but cheap/bounded -- explicitly
    # allowed by the permissions matrix. Only Opus and Sonnet represent the
    # "unbounded subscription cost" concern.
    if _is_metered(parent_executor) and child_executor in HIGH_COST_SUBSCRIPTION:
        parent_provider = _EXECUTOR_PROVIDERS.get(parent_executor, "?")
        child_provider = _EXECUTOR_PROVIDERS.get(child_executor, "?")
        return False, (f"metered->high-cost-subscription dispatch denied: "
                       f"{parent_executor} ({parent_provider}) cannot spawn "
                       f"{child_executor} ({child_provider}) -- cost-asymmetric: "
                       f"metered parent budget cannot account for "
                       f"Opus/Sonnet subscription costs")

    # Load matrix permissions
    permissions = _load_permissions(matrix_path)

    key = f"{parent_executor}.{child_executor}"
    if permissions.get(key, False):
        return True, "Allowed by permissions matrix"

    return False, (f"Permission denied: {parent_executor} -> {child_executor} "
                   f"not in permissions matrix")


def _load_permissions(matrix_path: str = None) -> dict:
    """Load the permissions table from dispatch_matrix.toml."""
    if not matrix_path or not tomllib:
        return _default_permissions()

    path = Path(matrix_path)
    if not path.exists():
        return _default_permissions()

    with open(path, "rb") as f:
        matrix = tomllib.load(f)

    return matrix.get("nested_dispatch", {}).get("permissions", {})


def _default_permissions() -> dict:
    """Default permissions when no matrix file is available."""
    return {
        "opus.sonnet": True,
        "opus.haiku": True,
        "opus.kimi": True,
        "opus.deepseek": True,
        "opus.ollama-local": True,
        "opus.gemini": True,
        "sonnet.haiku": True,
        "sonnet.kimi": True,
        "sonnet.deepseek": True,
        "sonnet.ollama-local": True,
        "sonnet.gemini": True,
        "kimi.haiku": True,
        "kimi.ollama-local": True,
        "deepseek.haiku": True,
        "deepseek.kimi": True,
        "deepseek.ollama-local": True,
    }
