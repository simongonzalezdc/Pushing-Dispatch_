"""Mandatory recurring job contracts for the utilization control plane."""

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class JobContract:
    name: str
    trigger: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    owner: str
    retry_limit: int = 2
    worker_auto_retry: bool = False
    dispatch_brief: str = ""


MANDATORY_JOBS = (
    JobContract("readiness_sweep", "before_batch_or_schedule", ("matrix", "availability", "cooldowns"), ("readiness", "snapshot"), "scheduler", dispatch_brief="Perform a trivial mechanical status check and return compact structured data."),
    JobContract("entitlement_refresh", "renewal_quota_or_stale", ("entitlements", "usage"), ("snapshot", "renewal_risk"), "policy", dispatch_brief="Extract and normalize current entitlement evidence; do not make purchases or account changes."),
    JobContract("snapshot_generation", "evidence_change", ("dispatch_state", "provider_mapping"), ("snapshot",), "snapshot_store", dispatch_brief="Perform a trivial mechanical transformation into a deterministic utilization snapshot."),
    JobContract("renewal_review", "underused_exhausted_or_unhealthy", ("snapshot", "thresholds"), ("advisory",), "policy", dispatch_brief="Perform a hard adversarial review of utilization evidence and produce advisory-only renewal recommendations."),
    JobContract("backlog_triage", "queue_age_or_review_cadence", ("queue", "outcomes", "availability"), ("work_recommendation",), "scheduler", dispatch_brief="Triage the supplied backlog into a concise prioritized recap without external actions."),
    JobContract("html_regeneration", "snapshot_or_advisory_change", ("snapshots", "advisories"), ("html",), "renderer", dispatch_brief="Perform a trivial mechanical render of structured utilization data into accessible HTML."),
)


def contracts() -> list[dict]:
    return [asdict(job) for job in MANDATORY_JOBS]


def validate_registry() -> None:
    names = [job.name for job in MANDATORY_JOBS]
    if len(names) != 6 or len(set(names)) != 6:
        raise ValueError("exactly six unique mandatory job families are required")
    if any(job.retry_limit > 2 or job.worker_auto_retry for job in MANDATORY_JOBS):
        raise ValueError("job retry policy violates the control-plane contract")
