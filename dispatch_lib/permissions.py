"""
Nested dispatch permission checks.

The permissions matrix lives in dispatch_matrix.toml under
[nested_dispatch.permissions]. Each entry: parent.child = true|false.
Missing entries are treated as denied.

Hard rules (always enforced, cannot be overridden by matrix):
  - Self-dispatch denied (loop prevention)
  - Leaf executors cannot dispatch (haiku, minimax, ollama-local)
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

# Executors with high subscription cost (metered parents should not spawn these)
HIGH_COST_SUBSCRIPTION = {"opus", "sonnet"}


def check_nested_permission(
    parent_executor: str,
    child_executor: str,
    matrix_path: str = None,
) -> tuple[bool, str]:
    """Check if parent_executor is allowed to dispatch child_executor.

    Returns: (allowed: bool, reason: str)
    """
    # Hard rule: self-dispatch always denied
    if parent_executor == child_executor:
        return False, f"Self-dispatch denied: {parent_executor} cannot spawn {parent_executor} (loop risk)"

    # Hard rule: leaf executors cannot dispatch
    if parent_executor in LEAF_EXECUTORS:
        return False, f"Leaf executor {parent_executor} cannot dispatch sub-workers"

    # Load matrix permissions
    permissions = _load_permissions(matrix_path)

    key = f"{parent_executor}.{child_executor}"
    if permissions.get(key, False):
        return True, "Allowed by permissions matrix"

    return False, f"Permission denied: {parent_executor} -> {child_executor} not in permissions matrix"


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
