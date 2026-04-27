"""
Auto-routing: pick the best executor for a brief.

Reads the brief (token count, keywords, explicit executor field)
and the dispatch matrix to select the cheapest executor that fits.
"""

import re
from pathlib import Path

from .context_budget import estimate_tokens

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None


# Keyword patterns that influence executor selection
LONG_CONTEXT_KEYWORDS = re.compile(
    r"(summarize|summarise|analyze|analyse|review|audit)\s+(all|every|each|the entire)",
    re.IGNORECASE,
)

MECHANICAL_KEYWORDS = re.compile(
    r"(rename|refactor|lint|format|fix typo|add comment|update import)",
    re.IGNORECASE,
)

HARD_CODING_KEYWORDS = re.compile(
    r"(implement|architect|design|debug|optimize|complex logic)",
    re.IGNORECASE,
)


def auto_route(
    brief_text: str,
    mode: str,
    matrix_path: str = None,
    explicit_executor: str = None,
) -> str:
    """Select an executor for the given brief and mode.

    Priority:
      1. Explicit executor (if provided and valid for mode)
      2. Routing heuristics based on brief content
      3. Default executor for mode

    Returns: executor name (e.g. "sonnet", "kimi", "haiku")
    """
    if explicit_executor:
        return explicit_executor

    token_count = estimate_tokens(brief_text)

    # Long context (>50K tokens): prefer large-window executors
    if token_count > 50_000 or LONG_CONTEXT_KEYWORDS.search(brief_text):
        return "kimi"

    # Mechanical/trivial tasks: prefer cheap executors
    if mode == "task" and token_count < 5_000 and MECHANICAL_KEYWORDS.search(brief_text):
        return "haiku"

    # Hard coding problems: prefer reasoning-capable executors
    if HARD_CODING_KEYWORDS.search(brief_text):
        if mode == "breakout":
            return "opus"
        return "sonnet"

    # Default by mode
    defaults = {
        "breakout": "sonnet",
        "task": "sonnet",
        "consult": "opus",
    }
    return defaults.get(mode, "sonnet")


def detect_mode_from_keywords(brief_text: str) -> str | None:
    """Guess the appropriate mode from brief content.

    Returns None if no strong signal.
    """
    text_lower = brief_text.lower()
    if any(kw in text_lower for kw in ["plan", "architect", "design", "orchestrate"]):
        return "breakout"
    if any(kw in text_lower for kw in ["fix", "rename", "lint", "update", "edit"]):
        return "task"
    return None
