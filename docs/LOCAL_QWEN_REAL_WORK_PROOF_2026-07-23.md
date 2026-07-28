# Local Qwen real-work proof — 2026-07-23

## BLUF

The governed NUC lanes now complete real work without cloud inference:

- Qwen 3.5 35B completed a two-document operational audit at 32,768 context.
- A distinct Qwen 3.5 27B reviewed that audit.
- Qwen 3.6 35B made the requested edit to `docs/PROVIDERS.md`.

All three successful runs proved exact model/runtime identity, remained below
the 90°C runtime cutoff, recorded no provider-metered cost, restored the
resident Qwen 3.6 27B lane and watchdog, and left production routing unchanged.
The outputs were not accepted blindly: both audit models made stale or
incorrect claims, while the tightly specified coding edit was correct.

## Crash root cause and deterministic repair

The computer reset because the CPU thermal limit tripped. Two copies of the
resident model had been loaded simultaneously by the dedicated service and the
Studio/proxy path. The boot also carried a deprecated `amdgpu.gttsize`
override that disagreed with the driver's 64 GiB TTM limit.

The repair:

- removed only the deprecated GTT override and regenerated GRUB;
- disabled Studio and its proxy;
- retained exactly one resident Qwen 3.6 27B service and watchdog;
- fixed the GPU performance level at `low` for boot, resident work, on-demand
  activation, thermal rollback, and deadman restoration;
- capped Qwen 3.5 35B prompt threads and physical batch size;
- rejects activation above 85°C;
- samples Tctl every two seconds and restores at 90°C or on sensor failure.

The unrestricted resident lane was observed at 97.6°C. With the hardware cap,
the resident stabilized around 65–73°C. The successful 35B canaries remained
below the cutoff.

## Real work receipts

| Worker | Local work | Exact context | Result |
|---|---|---:|---|
| `w-b3c7-task` | Audited `docs/PROVIDERS.md` and `docs/TROUBLESHOOTING.md` | 32,768 | Passed; useful findings plus two rejected mistakes |
| `w-06ca-task` | Independently reviewed the audit | 8,192 | Passed; correctly rejected lane-removal advice, but repeated stale context/proxy claims |
| `w-b248-task` | Edited `docs/PROVIDERS.md` | 8,192 | Passed; requested diff was correct |

Identity receipts:

- `w-b3c7-task`: Qwen 3.5 35B-A3B model SHA
  `3b46d1066bc91cc2d613e3bc22ce691dd77e6f0d33c9060690d24ce6de494375`;
  runtime SHA
  `a6a8f74f9730b09ada07cf467410fc41dbcdd894d6430a2d0cdad2d93e5ff944`.
- `w-06ca-task`: Qwen 3.5 27B model SHA
  `84b5f7f112156d63836a01a69dc3f11a6ba63b10a23b8ca7a7efaf52d5a2d806`;
  runtime SHA
  `a6a8f74f9730b09ada07cf467410fc41dbcdd894d6430a2d0cdad2d93e5ff944`.
- `w-b248-task`: Qwen 3.6 35B-A3B model SHA
  `4ac6a06bce551257267f49ad2226f8671a22519ccc1a4dde9d5b433d1f2a410d`;
  runtime SHA
  `eb0726d558964531e1f3687f388fde9bc63d9864debadfe050cd4c3decb98cda`.

Every receipt records `thermal_trip: null`, `restoration.restored: true`,
`production_routing_changed: false`, and `metered_cost_usd: null`. Null cost is
not a manufactured dollar-savings claim; it means there was no provider meter.

Artifact hashes:

| Artifact | SHA-256 |
|---|---|
| `logs/w-b3c7-task.log` | `a0381091a7e1d211320522a0d057423125b3071b8708c8d9a3cd1c652f6eeb5e` |
| `receipts/nuc-workcells/w-b3c7-task.json` | `9b290a49f14d78ab311b5697dd93b64837634b20ea1b22603e7053cf1f3c8aa4` |
| `logs/w-06ca-task.log` | `6fc6eb5d851cb3e56f9c024563211adc4dfae35bfd940fd6cfdac11b8dbc325b` |
| `receipts/nuc-workcells/w-06ca-task.json` | `e58ee059c7b3703b1c652ed90f704dfad075c6b25986232e97e7fb87cbc9d7ed` |
| `logs/w-b248-task.log` | `1e0214dc6c2c82f6b698b2229bb0d6810bd3e9b52a3ad9aadf274d697b7a2a47` |
| `receipts/nuc-workcells/w-b248-task.json` | `4744a2372ec1d6dd506f4240bb167f69c771f5890b7c45e47e72ae6765280946` |

## Admission boundary

At the time of these canaries, this proved only that the local lanes could
displace bounded cloud-model work under validation; automatic routing remained
unchanged.

## Post-proof automatic task admission — 2026-07-23

The operator subsequently authorized fixing the underused local routing and
the unsafe mechanical-task classifier. Automatic admission is now deliberately
task-class scoped:

| Deterministic class | First route | Input ceiling |
|---|---|---:|
| Atomic typo, one-file lint/format, or local rename | Dell Qwen 3.5 2B plus mandatory resident-NUC validation | 5,000 |
| Bounded general work | Qwen 3.5 35B-A3B | 24,000 |
| Bounded independent review | Qwen 3.5 27B | 5,000 |
| Bounded coding | Qwen 3.6 35B-A3B | 5,000 |

Complex or risky scope is evaluated before mechanical keywords.
Repository-wide, multi-file, authentication, authorization, security,
database/schema, migration, production, architectural, adversarial, visual,
long-context, consult, and breakout work cannot enter these local automatic
tiers. Oversized briefs return to the existing standard or long-context tier.

Verification after admission: 176 unit tests passed; both matrices validated;
Python compilation and `git diff --check` passed; all five local executors were
live and out of cooldown. Read-only CLI probes selected the intended local
executor for each bounded class and escalated broad authentication refactoring
and repository-wide linting to `grok-build`.
