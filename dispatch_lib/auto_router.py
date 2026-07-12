"""Auto-routing: pick the best AVAILABLE executor for a brief.

The dispatch matrix is the source of truth. The router maps a brief to a tier,
then filters the tier's ordered candidate list by required capabilities and
returns the first executor that is mode-allowed, available, and not in cooldown.
"""
import re
from pathlib import Path

from .context_budget import estimate_tokens
from .availability import available_set
from .lane_health import in_cooldown

try:
    import tomllib
except ImportError:  # pragma: no cover
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None


class NoExecutorAvailable(RuntimeError):
    """Raised when no capable, available executor exists for a brief."""


LONG_CONTEXT_KEYWORDS = re.compile(
    r"(summarize|summarise|analyze|analyse|review|audit)\s+(all|every|each|the entire)",
    re.IGNORECASE,
)
MECHANICAL_KEYWORDS = re.compile(
    r"(rename|refactor|lint|format|fix typo|add comment|update import)", re.IGNORECASE,
)
HARD_CODING_KEYWORDS = re.compile(
    r"(implement|architect|design|debug|optimize|complex logic|concurren)", re.IGNORECASE,
)
VISION_REQUIREMENT_KEYWORDS = re.compile(
    r"\bvision\s+required\b|\b(?:screenshot|image)\b|"
    r"\b(?:render(?:ed)?\s+(?:review|inspection)|review\s+(?:the\s+)?render(?:ed)?)\b",
    re.IGNORECASE,
)


def _load_matrix(matrix_path):
    if not matrix_path or not tomllib:
        return {}
    path = Path(matrix_path)
    if not path.exists():
        return {}
    with open(path, "rb") as f:
        return tomllib.load(f)


def _candidates(route_cfg, list_key, legacy_keys):
    """Ordered candidate list. Falls back to legacy single-value keys."""
    if route_cfg.get(list_key):
        return list(route_cfg[list_key])
    out = []
    for k in legacy_keys:
        v = route_cfg.get(k)
        if v:
            out.append(v)
    return out


def _tier(brief_text, mode, route_cfg):
    """Return (list_key, legacy_keys) for the brief's tier."""
    tokens = estimate_tokens(brief_text)
    long_threshold = int(route_cfg.get("long_context_threshold_tokens", 50_000))
    if tokens > long_threshold or LONG_CONTEXT_KEYWORDS.search(brief_text):
        return "long_context_candidates", ["long_context_executor"]
    # Explicit consult mode is authoritative over coding-keyword heuristics:
    # a consult is advisory/review work and should prefer the consult tier.
    if mode == "consult":
        return "consult_candidates", ["default_consult"]
    if HARD_CODING_KEYWORDS.search(brief_text):
        if mode == "breakout":
            return "hard_breakout_candidates", ["hard_coding_breakout_executor", "default_breakout"]
        return "hard_task_candidates", ["hard_coding_task_executor", "default_task"]
    if mode == "breakout":
        return "hard_breakout_candidates", ["default_breakout"]
    trivial_threshold = int(route_cfg.get("trivial_threshold_tokens", 5_000))
    if tokens < trivial_threshold and (mode == "task" or MECHANICAL_KEYWORDS.search(brief_text)):
        return "trivial_candidates", ["trivial_executor", "default_task"]
    return "standard_candidates", ["default_task"]


def _mode_allowed(matrix, executor, mode):
    cfg = matrix.get("executors", {}).get(executor, {})
    return mode in cfg.get("allowed_modes", [])


def required_capabilities(brief_text):
    """Return capabilities the brief requires before candidates are ranked."""
    return {"vision"} if VISION_REQUIREMENT_KEYWORDS.search(brief_text) else set()


def missing_capabilities(matrix, executor, required):
    """Return declared capabilities missing from an executor.

    Missing metadata is deliberately treated as no capabilities, so visual
    requests fail closed until the matrix explicitly declares vision support.
    """
    capabilities = matrix.get("executors", {}).get(executor, {}).get("capabilities", [])
    return sorted(required - set(capabilities))


def auto_route(brief_text, mode, matrix_path=None, explicit_executor=None,
               matrix_dict=None, return_tier=False):
    if explicit_executor and explicit_executor != "auto":
        return (explicit_executor, "explicit") if return_tier else explicit_executor

    matrix = matrix_dict if matrix_dict is not None else _load_matrix(matrix_path)
    route_cfg = matrix.get("auto_route", {})

    avail = available_set(matrix)
    list_key, legacy = _tier(brief_text, mode, route_cfg)
    required = required_capabilities(brief_text)

    # Search order: tier candidates first, then a broad safety net of every
    # mode-capable executor in matrix order.
    order = _candidates(route_cfg, list_key, legacy)
    order += [e for e in matrix.get("executors", {}) if e not in order]
    capability_rejections = []
    eligible_order = []

    # Capabilities are a hard precondition, not a ranking preference.
    for executor in order:
        missing = missing_capabilities(matrix, executor, required)
        if missing:
            capability_rejections.append((executor, missing))
        else:
            eligible_order.append(executor)

    for executor in eligible_order:
        if not _mode_allowed(matrix, executor, mode):
            continue
        if executor not in avail:
            continue
        if in_cooldown(executor):
            continue
        return (executor, list_key) if return_tier else executor

    capability_detail = ""
    if capability_rejections:
        rejected = "; ".join(
            f"{executor} (missing {', '.join(missing)} capability)"
            for executor, missing in capability_rejections
        )
        capability_detail = f" requires {', '.join(sorted(required))}; rejected: {rejected}."
    raise NoExecutorAvailable(
        f"No available executor for mode={mode}{capability_detail} "
        "Run 'pushing-dispatch doctor' to see which providers need attention."
    )


def detect_mode_from_keywords(brief_text):
    text_lower = brief_text.lower()
    if any(kw in text_lower for kw in ["plan", "architect", "design", "orchestrate"]):
        return "breakout"
    if any(kw in text_lower for kw in ["fix", "rename", "lint", "update", "edit"]):
        return "task"
    return None
