# Utilization control plane

The control plane turns the live Dispatch matrix, availability, cooldowns,
outcomes, and optional account evidence into versioned utilization snapshots
and a read-only HTML report.

## Authority boundary

Pushing Dispatch remains the sole authority for executor selection, routing,
availability, and cooldowns. The HTML renderer writes only its report. It has
no account-management or cancellation capability.

## Run a cycle

```bash
python3 cli.py utilization --probe --json
```

Optional current account evidence is a JSON object keyed by executor:

```json
{
  "example-executor": {
    "provider_class": "quota_entitlement",
    "evidence_fresh": true,
    "paid": true,
    "numerator": 25,
    "denominator": 100,
    "unit": "tokens_used_per_tokens_allocated",
    "exhausted": false,
    "renewal_due": false,
    "confidence": "high",
    "source_artifacts": ["provider_account_snapshot"],
    "source_event_ids": ["redacted-stable-evidence-id"]
  }
}
```

Pass it with `--entitlements evidence.json`. Do not put credentials, raw
receipts, prompts, or private memory in this file. Missing paid-account
evidence fails closed as `unknown`; local capacity may rely on live health,
mode, and executor availability.

## Provider classes

- `flat_rate_annual`
- `quota_entitlement`
- `credit_balance`
- `usage_metered`
- `local_capacity`

## Retry and action policy

Control-plane read lookups may retry at most twice with bounded backoff.
Workers never auto-retry. Renewal and cancellation results are advisories only.
Any cancellation, renewal, purchase, refund, or other financial change requires
explicit human confirmation outside this control plane.

## Rollback

1. Stop invoking `cli.py utilization` from any scheduler.
2. Leave the existing matrix, availability, cooldown, budget, outcome, and
   lane-health ledgers in place.
3. Remove or ignore generated utilization snapshots and the HTML report only
   if their fidelity is suspect.
4. Resume normal Dispatch operation; no legacy routing behavior needs to be
   restored because the renderer never owned routing state.
