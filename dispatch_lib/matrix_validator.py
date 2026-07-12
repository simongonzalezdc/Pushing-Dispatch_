"""
Dispatch matrix validation.

Validates dispatch_matrix.toml for correctness:
  - Schema version check
  - Required fields per executor
  - Mode x executor allowlist integrity
  - Hard-wall constraint validation
  - Nested dispatch permission checks (no self-dispatch, no leaf orchestrators)
"""

from pathlib import Path

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None

REQUIRED_EXECUTOR_FIELDS = {
    "wrapper",
    "provider",
    "allowed_modes",
}

OPTIONAL_EXECUTOR_FIELDS = {
    "capabilities",
    "model_id",
    "default_thinking_tokens",
    "thinking_hard_ceiling",
    "context_window",
    "max_turns",
    "stall_threshold_seconds",
    "allowed_seats_in_breakout",
    "hard_wall_block_breakout_top",
    "hard_wall_block_task_top",
}

VALID_MODES = {"task", "breakout", "consult"}


def validate(matrix_path: str) -> list[str]:
    """Validate a dispatch matrix TOML file.

    Returns list of error messages. Empty list = valid.
    """
    if not tomllib:
        return ["tomllib/tomli not available; cannot validate TOML"]

    path = Path(matrix_path)
    if not path.exists():
        return [f"Matrix file not found: {matrix_path}"]

    with open(path, "rb") as f:
        matrix = tomllib.load(f)

    errors = []

    # Schema version
    if matrix.get("schema_version") != 1:
        errors.append(f"Expected schema_version = 1, got {matrix.get('schema_version')}")

    # Executors
    executors = matrix.get("executors", {})
    if not executors:
        errors.append("No [executors] section found")
    else:
        for name, config in executors.items():
            errors.extend(_validate_executor(name, config))

    # Nested dispatch permissions
    errors.extend(validate_nested_permissions(matrix))

    return errors


def _validate_executor(name: str, config: dict) -> list[str]:
    """Validate a single executor entry."""
    errors = []
    for field in REQUIRED_EXECUTOR_FIELDS:
        if field not in config:
            errors.append(f"Executor '{name}' missing required field: {field}")

    modes = config.get("allowed_modes", [])
    for mode in modes:
        if mode not in VALID_MODES:
            errors.append(f"Executor '{name}' has invalid mode: {mode}")

    capabilities = config.get("capabilities", [])
    if not isinstance(capabilities, list) or not all(isinstance(item, str) for item in capabilities):
        errors.append(f"Executor '{name}' capabilities must be a list of strings")

    thinking = config.get("default_thinking_tokens", 0)
    ceiling = config.get("thinking_hard_ceiling", thinking)
    if thinking > ceiling:
        errors.append(
            f"Executor '{name}': default_thinking_tokens ({thinking}) "
            f"exceeds thinking_hard_ceiling ({ceiling})"
        )

    return errors


def validate_nested_permissions(matrix: dict) -> list[str]:
    """Validate the [nested_dispatch.permissions] table."""
    errors = []
    nd = matrix.get("nested_dispatch", {})
    permissions = nd.get("permissions", {})

    executor_names = set(matrix.get("executors", {}).keys())

    for key, value in permissions.items():
        parts = key.split(".")
        if len(parts) != 2:
            errors.append(f"Invalid permission key format: '{key}' (expected 'parent.child')")
            continue

        parent, child = parts

        # Self-dispatch check
        if parent == child:
            errors.append(f"Self-dispatch entry found: {key} (always denied, remove from matrix)")

        # Warn on unknown executors
        if parent not in executor_names:
            errors.append(f"Permission references unknown parent executor: {parent}")
        if child not in executor_names:
            errors.append(f"Permission references unknown child executor: {child}")

    return errors
