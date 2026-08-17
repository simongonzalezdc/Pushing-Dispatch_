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
    "kimi-k3-cli": 1_048_576,
    "kimi-k3-kyanite": 1_048_576,
    "kimi-k3-key": 1_048_576,
    "kimi-k3-ollama": 1_048_576,
    "zai-glm": 1_000_000,
    "minimax-m3": 512_000,
    "codex-luna": 272_000,
    "codex-terra": 272_000,
    "codex-sol": 272_000,
    "agy-gemini-flash": 1_000_000,
    "dsh": 131_072,
    "deepseek-v4-pro": 131_072,
    "deepseek-v4-flash": 131_072,
    "kilo-free-auto": 128_000,
    "lm-studio": 131_072,
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
