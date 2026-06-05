"""
Context budget checking.

Pre-flight validation that a brief + included packs fit within
the target executor's context window. Prevents "prompt too long"
failures at runtime.
"""

import os
from pathlib import Path


# Chars-per-token estimate. Conservative (real ratio ~3.5 for English).
CHARS_PER_TOKEN = 4

# Default context windows by provider (tokens).
DEFAULT_CONTEXT_WINDOWS = {
    "opus": 200_000,
    "sonnet": 200_000,
    "haiku": 200_000,
    "kimi-coding": 256_000,
    "kimi-moonshot": 262_144,
    "kimi": 262_144,
    "kimi-think": 262_144,
    "deepseek": 128_000,
    "minimax": 128_000,
    "ollama-local": 8_000,
}

# Reserved tokens for system prompt, tool definitions, response.
OVERHEAD_TOKENS = 15_000


def estimate_tokens(text: str) -> int:
    """Estimate token count from text length."""
    return len(text) // CHARS_PER_TOKEN


def check_budget(
    brief_text: str,
    executor: str,
    context_windows: dict = None,
) -> dict:
    """Check if brief fits within executor's context window.

    Returns:
        {
            "fits": bool,
            "estimated_tokens": int,
            "available_tokens": int,
            "executor": str,
        }
    """
    windows = context_windows or DEFAULT_CONTEXT_WINDOWS
    max_tokens = windows.get(executor, 200_000)
    available = max_tokens - OVERHEAD_TOKENS
    estimated = estimate_tokens(brief_text)

    return {
        "fits": estimated <= available,
        "estimated_tokens": estimated,
        "available_tokens": available,
        "executor": executor,
    }


def check_budget_for_file(
    brief_path: str,
    executor: str,
    context_windows: dict = None,
) -> dict:
    """Check budget for a brief file on disk."""
    text = Path(brief_path).read_text()
    return check_budget(text, executor, context_windows)
