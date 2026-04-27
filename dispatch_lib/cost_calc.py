"""
Per-provider cost calculation.

Reads pricing from dispatch_pricing.toml (if available) or uses
sensible defaults. Computes per-turn and per-worker cost estimates.
"""

import os
from pathlib import Path

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None


# Default pricing per 1M tokens (USD). Override via dispatch_pricing.toml.
DEFAULT_PRICING = {
    "anthropic": {"input": 3.00, "output": 15.00},
    "moonshot": {"input": 1.00, "output": 3.00},
    "deepseek": {"input": 0.50, "output": 2.00},
    "minimax": {"input": 0.80, "output": 2.40},
    "ollama": {"input": 0.00, "output": 0.00},
}


def load_pricing(pricing_path: str = None) -> dict:
    """Load pricing from TOML file, falling back to defaults."""
    if pricing_path and Path(pricing_path).exists() and tomllib:
        with open(pricing_path, "rb") as f:
            return tomllib.load(f).get("pricing", DEFAULT_PRICING)
    return DEFAULT_PRICING


def cost_for_turn(
    provider: str,
    tokens_in: int,
    tokens_out: int,
    pricing: dict = None,
) -> float:
    """Calculate USD cost for a single turn."""
    if pricing is None:
        pricing = DEFAULT_PRICING
    rates = pricing.get(provider, {"input": 0.0, "output": 0.0})
    cost = (tokens_in / 1_000_000) * rates["input"] + (tokens_out / 1_000_000) * rates["output"]
    return round(cost, 6)


def per_worker_cap(provider: str, pricing: dict = None) -> float:
    """Estimate a reasonable per-worker cost cap based on provider pricing.

    Heuristic: assume 50K input + 10K output tokens as a typical worker session.
    """
    return cost_for_turn(provider, 50_000, 10_000, pricing)
