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
ATOMIC_MECHANICAL_KEYWORDS = re.compile(
    r"(?:fix|correct)(?:\s+(?:a|the))?\s+(?:single\s+)?typo\b|"
    r"add(?:\s+(?:a|the))?\s+comment|update(?:\s+(?:a|the))?\s+import",
    re.IGNORECASE,
)
SCOPED_MECHANICAL_KEYWORDS = re.compile(
    r"\b(rename|lint|format)\b",
    re.IGNORECASE,
)
ATOMIC_SCOPE_KEYWORDS = re.compile(
    r"\b(one|single|this|exact|local)\b|\b(identifier|variable|function|line|file)\b",
    re.IGNORECASE,
)
COMPLEX_OR_RISKY_KEYWORDS = re.compile(
    r"\b(authentication|authorization|cryptograph\w*|security[- ]sensitive|"
    r"production|deployment|distributed|subsystem|migration|breaking change|"
    r"database|schema|monorepo|multi[- ]file|cross[- ]module|repository[- ]wide|"
    r"project[- ]wide)\b|"
    r"\b(?:entire|whole)\s+(?:codebase|repository|repo|project)\b|"
    r"\b(?:all|every)\s+(?:the\s+)?files?\b|"
    r"\bacross\b.{0,80}\b(?:files?|modules?|codebase|repository|repo|project)\b|"
    r"\b(?:two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|[2-9]\d*)\s+files?\b",
    re.IGNORECASE,
)
HARD_CODING_KEYWORDS = re.compile(
    r"(architect|debug|optimi[sz]e|complex logic|concurren|race condition|"
    r"hard implementation|multi[- ]module|distributed system|adversarial review)",
    re.IGNORECASE,
)
LOCAL_CODING_KEYWORDS = re.compile(
    r"\b(implement|code|patch|edit|modify|refactor)\b|"
    r"\blocal\s+coding\b|\bself[- ]scaffold\b|\bnucbox\b|\bornith\b|"
    r"\b(?:fix|repair)\b.{0,40}\b(?:bug|test|function|script|config(?:uration)?)\b|"
    r"\b(?:add|update)\b.{0,40}\b(?:test|function|validator|script|config(?:uration)?)\b|"
    r"\bpure\s+function\b|\bunit\s+tests?\b|\bsingle[- ]file\b",
    re.IGNORECASE,
)
LOCAL_REVIEW_KEYWORDS = re.compile(
    r"\b(review|verify|validate|compare|check)\b|"
    r"\bcontradiction\w*\b|\bgrounded findings?\b",
    re.IGNORECASE,
)
LOCAL_GENERAL_KEYWORDS = re.compile(
    r"\b(summarize|summarise|analyze|analyse|extract|draft|classify|rewrite|"
    r"document|synthesize|synthesise|audit)\b",
    re.IGNORECASE,
)
# S-073 fix: bare 'screenshot'/'image' nouns false-positived research briefs
# into vision-only lanes. Vision is required for visual ACTIONS, not mentions.
VISION_REQUIREMENT_KEYWORDS = re.compile(
    r"\bvision\s+required\b|"
    r"\b(?:analyz|analys|describ|inspect|review|compare|read|interpret) e?\b[^.]{0,40}\b(?:screenshot|image|render|screenshot[s]?)\b|"
    r"\b(?:screenshot|image|render(?:ed)?)\b[^.]{0,40}\b(?:analyz|analys|describ|inspect|review|compar)\b|"
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
    if HARD_CODING_KEYWORDS.search(brief_text) or COMPLEX_OR_RISKY_KEYWORDS.search(brief_text):
        if mode == "breakout":
            return "hard_breakout_candidates", ["hard_coding_breakout_executor", "default_breakout"]
        return "hard_task_candidates", ["hard_coding_task_executor", "default_task"]
    if mode == "breakout":
        return "hard_breakout_candidates", ["default_breakout"]
    trivial_threshold = int(route_cfg.get("trivial_threshold_tokens", 5_000))
    inherently_atomic = ATOMIC_MECHANICAL_KEYWORDS.search(brief_text)
    explicitly_scoped = (
        SCOPED_MECHANICAL_KEYWORDS.search(brief_text)
        and ATOMIC_SCOPE_KEYWORDS.search(brief_text)
    )
    if tokens < trivial_threshold and (inherently_atomic or explicitly_scoped):
        return "trivial_candidates", ["trivial_executor", "default_task"]
    if mode == "task":
        local_coding_max = int(route_cfg.get("local_coding_max_tokens", 0))
        if (
            route_cfg.get("local_coding_candidates")
            and tokens <= local_coding_max
            and LOCAL_CODING_KEYWORDS.search(brief_text)
        ):
            return "local_coding_candidates", ["default_task"]
        local_review_max = int(route_cfg.get("local_review_max_tokens", 0))
        if (
            route_cfg.get("local_review_candidates")
            and tokens <= local_review_max
            and LOCAL_REVIEW_KEYWORDS.search(brief_text)
        ):
            return "local_review_candidates", ["default_task"]
        local_general_max = int(route_cfg.get("local_general_max_tokens", 0))
        if (
            route_cfg.get("local_general_candidates")
            and tokens <= local_general_max
            and LOCAL_GENERAL_KEYWORDS.search(brief_text)
        ):
            return "local_general_candidates", ["default_task"]
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
    matrix = matrix_dict if matrix_dict is not None else _load_matrix(matrix_path)
    required = required_capabilities(brief_text)
    if explicit_executor and explicit_executor != "auto":
        cfg = matrix.get("executors", {}).get(explicit_executor)
        if cfg is None:
            raise NoExecutorAvailable(f"Explicit executor '{explicit_executor}' is not declared in the dispatch matrix.")
        if not _mode_allowed(matrix, explicit_executor, mode):
            raise NoExecutorAvailable(
                f"Explicit executor '{explicit_executor}' does not allow mode={mode}."
            )
        missing = missing_capabilities(matrix, explicit_executor, required)
        if missing:
            raise NoExecutorAvailable(
                f"Explicit executor '{explicit_executor}' is missing required capability: {', '.join(missing)}."
            )
        if explicit_executor not in available_set(matrix) or in_cooldown(explicit_executor):
            raise NoExecutorAvailable(
                f"Explicit executor '{explicit_executor}' is unavailable. "
                "Run 'pushing-dispatch doctor' to see which providers need attention."
            )
        return (explicit_executor, "explicit") if return_tier else explicit_executor

    route_cfg = matrix.get("auto_route", {})

    avail = available_set(matrix)
    list_key, legacy = _tier(brief_text, mode, route_cfg)

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

    # Wave-2 FM-23: auto-routing skips lanes whose 30-day error rate exceeds
    # the threshold (min-sample guarded). Explicit executor choices are never
    # filtered — the operator's call stands.
    _threshold = float(route_cfg.get("bad_lane_error_threshold", 0.40))
    _min_n = int(route_cfg.get("bad_lane_min_samples", 5))
    _skipped_bad = []
    if eligible_order:
        from dispatch_lib import outcomes as _outcomes
        _kept = []
        for executor in eligible_order:
            rate, n = _outcomes.error_rate_30d(executor, min_samples=_min_n)
            if rate is not None and rate > _threshold:
                _skipped_bad.append(f"{executor} ({rate:.0%} error, n={n})")
                continue
            _kept.append(executor)
        eligible_order = _kept

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
    _bad_detail = f" bad-lane skips: {'; '.join(_skipped_bad)}." if _skipped_bad else ""
    raise NoExecutorAvailable(
        f"No available executor for mode={mode}{capability_detail}{_bad_detail} "
        "Run 'pushing-dispatch doctor' to see which providers need attention."
    )


def detect_mode_from_keywords(brief_text):
    text_lower = brief_text.lower()
    if any(kw in text_lower for kw in ["plan", "architect", "design", "orchestrate"]):
        return "breakout"
    if any(kw in text_lower for kw in ["fix", "rename", "lint", "update", "edit"]):
        return "task"
    return None
