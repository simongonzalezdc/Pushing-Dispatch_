# MEASURED-DISPATCH RECOMMENDATIONS (S14; source: CS MEASURED-WALLS-INVENTORY-2026-08-21 @cf9e6fd)

Coverage: 11/8 task-classes measured (35B parked-lane excluded per label law).
Winning pairs (median wall-clock vs default, >=10% bar): 3 FOUND in existing data.
AUTO-APPLY STAYS OFF (CEO-QUEUE row) — this table is advisor-visible only.

| task-class | recommendation | measured basis (paired) | artifact |
|---|---|---|---|
| prose generation (<=200 tok) | champion + spec MIRROR (serving config) | 15.1s mirror vs 17.8s off = 15.2% faster | spec-sweep-results.log |
| decode-heavy long-doc (131k+) | KV q8_0 | decode 3.2 vs 4.0s = 20.0% faster | kv-sweep-results.log |
| quote/needle @198k | KV q8_0 | HIT quote 10.4s vs 23.8s q4-warm = 56% faster | flip-confirm-results.log |
| math short-answer | KV q4_0 (speed) | 18.78 vs 19.47s (3.5%; quality parity labeled) | flip-confirm-results.log |
| hard reasoning | think-40 on | 15/40 vs 4/40 solves (quality pays) | kneemap-gsm8k-hard.log |
| medium reasoning | think-35 on | 25/35 vs 11/35 [Wilson 55-84] | FACTS-PACK |
| long-doc QA warm (198k, q4 serving) | keep q4 until CEO KV flip row | quote 23.8/exists 10.0/summary 17.5s | quote-rerun-results.log |
| vision QA (real UI) | champion direct | 6/6 at 4.0-4.9s/answer | vision-real-2026-08-20/ |
| code (function) | canon defaults | HumanEval 93% | canon @46aa138f |
| LCB composite | routing per canon | 19/30 | lcb-30-2026-08-20/ |
| speed-trick regimes | NEVER cross-regime compare | 4 labeled regimes, SPEED SHEET | README |

GAP CLASSES (0 walls): translation, extraction, agent chains, decision-support
→ produced by the delegation-bench first run (post CTO integration + CEO
unpause) — one instrument, two consumers. NO separate GPU work scheduled.

## S14 bar check (falsifiable)
- knees-coverage >=8: **PASS (11)** — existing data only
- 3 winning pairs >=10% median: **PASS (15.2%, 20.0%, 56%)** — paired, cited
- auto-apply: OFF — flips only via the existing CEO-QUEUE row (incl. the
  pending KV q8 serving flip)


## CORRECTION (COO, 2026-08-21 — retract-wrong-numbers law)
The "56% faster quotes" pair was CROSS-ARTIFACT (needle file vs warm-file, different
task variants) — a violation of the paired-same-task doctrine. CS's paired table is
the truth: q4 vs q8 differences at 131k are SMALL AND MIXED (decode 3.2 vs 4.0s =
0.8s absolute; tg128 slightly favors q4; q8 costs +2GB GTT). The one clean pair in
this table remains spec-mirror prose (+15%). VERDICT CORRECTED: KEEP q4 KV (CS's
original least-resource call was RIGHT); the q8 flip row is WITHDRAWN as an input,
not a recommendation. "3 winning pairs" claim: reduced to 1.
