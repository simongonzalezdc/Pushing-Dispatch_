"""Provider accounting and advisory-only utilization policy."""

from __future__ import annotations

from typing import Any

LOCAL_PROVIDERS = {"ollama", "lm-studio"}
QUOTA_PROVIDERS = {"ollama-cloud", "kimi-cli"}
FLAT_RATE_PROVIDERS = {"openai-codex", "zai", "gjc", "agy", "grok-cli", "kilo-cli"}
VALID_ACTIONS = {"schedule", "assign_more_work", "reserve", "investigate", "consider_cancellation"}


def provider_class(cfg: dict[str, Any], entitlement: dict[str, Any] | None = None) -> str:
    explicit = (entitlement or {}).get("provider_class") or cfg.get("provider_class")
    if explicit:
        return explicit
    provider = cfg.get("provider", "")
    if provider in LOCAL_PROVIDERS:
        return "local_capacity"
    if provider in QUOTA_PROVIDERS:
        return "quota_entitlement"
    if provider in FLAT_RATE_PROVIDERS:
        return "flat_rate_annual"
    return "usage_metered"


def denominator_source(kind: str) -> str:
    return {
        "flat_rate_annual": "receipt_or_renewal_plus_live_usage",
        "quota_entitlement": "provider_quota_plus_live_usage",
        "credit_balance": "remaining_credit_plus_live_usage",
        "usage_metered": "spend_ledger_plus_billable_events",
        "local_capacity": "health_mode_and_executor_availability",
    }[kind]


def decide(*, available: bool, cooldown: bool, disabled: bool, evidence_fresh: bool,
           utilization: float, paid: bool, exhausted: bool = False) -> dict[str, str]:
    """Return a scheduling/advisory decision; never an external action."""
    if disabled:
        return {"status": "excluded", "recommendation": "investigate", "exclusion_reason": "matrix_disabled"}
    if exhausted:
        return {"status": "exhausted", "recommendation": "investigate", "exclusion_reason": "quota_exhausted"}
    if not evidence_fresh:
        return {"status": "unknown", "recommendation": "investigate", "exclusion_reason": "stale_or_missing_evidence"}
    if cooldown:
        return {"status": "cooldown", "recommendation": "reserve", "exclusion_reason": "active_cooldown"}
    if not available:
        return {"status": "unavailable", "recommendation": "investigate", "exclusion_reason": "health_or_auth_unavailable"}
    if paid and utilization < 0.10:
        return {"status": "healthy_underused", "recommendation": "assign_more_work", "exclusion_reason": ""}
    return {"status": "healthy", "recommendation": "schedule", "exclusion_reason": ""}


def renewal_advisory(snapshot: dict[str, Any], *, renewal_due: bool = False) -> str:
    """Return an advisory label. This function has no mutation capability."""
    if snapshot["provider_class"] == "local_capacity":
        return "not_applicable"
    status = snapshot["status"]
    value = float(snapshot["metric"]["value"])
    if status in {"unknown", "unavailable", "exhausted"}:
        return "investigate"
    if renewal_due and value < 0.10:
        return "consider_cancellation"
    if value < 0.35:
        return "assign_more_work"
    return "reserve"
