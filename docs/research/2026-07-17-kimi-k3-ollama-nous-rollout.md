# Kimi K3 rollout: Ollama Cloud and Nous Gateway

**Checked:** 2026-07-17 (America/Los_Angeles)  
**Question:** Is Ollama Cloud likely to receive Kimi K3 only after the open-weight release, and when can Hermes use K3 through an allowed subscription?

## Executive finding

There is **no published Ollama Cloud ETA**. The hypothesis that Ollama waits for the open-weight release is plausible, but not confirmed. Moonshot has committed to release the full K3 weights on **2026-07-27**, and says it is still aligning inference partners and open-source maintainers. That is the only authoritative future milestone found.

Nous Gateway is different: it is already serving `moonshotai/kimi-k3`. Hermes upstream merged the catalog change on 2026-07-16 and its maintainer recorded a successful live Nous `/v1/models` check. Hermes can use that route after a valid Nous Portal login; this machine did not have a Nous token at the time of checking.

## Confirmed facts

| Surface | Current status | Evidence |
| --- | --- | --- |
| Moonshot K3 API | Available now | Moonshot says K3 is available through its hosted K3 channels and API. |
| K3 open weights | Scheduled for 2026-07-27 | Moonshot's launch post explicitly commits to that date. |
| Nous Gateway | Available now | Hermes PR #65913 says `moonshotai/kimi-k3` was live on the Nous Portal `/v1/models` endpoint; the PR was merged July 16. |
| Ollama Cloud | Not available at this check | Authenticated `/v1/models` listed only older Kimi releases, not K3. `k3`, `kimi-k3`, and `moonshotai/kimi-k3` each returned HTTP 404. Public registry paths for K3 also returned HTTP 404. |
| Ollama schedule | No announcement or ETA | Ollama's own GitHub request for K3 Cloud is open without a maintainer schedule or commitment. |

## What can and cannot be inferred

### Supported inference

Ollama could reasonably wait until July 27: its normal route for a new open model is to publish a registry artifact after weights are available, and Moonshot specifically names open-source-maintainer alignment alongside the weight release. This makes July 27 the earliest evidence-backed planning milestone for an Ollama-native K3 rollout.

### Not supported

Do not treat July 27 as an Ollama launch date. Ollama Cloud can host models before, after, or independently of an open-weight release. Nous already proves that a hosted partner can make K3 available before the public weights. No Ollama or Moonshot source names Ollama as a launch partner or commits to a date.

## Operational decision

1. **Kimi subscription path:** use `kimi-k3-cli` only through the official Kimi CLI.
2. **Nous path:** inactive for this installation; do not route or budget against it.
3. **Ollama/Hermes path:** leave `kimi-k3-ollama` live-catalog-gated. It remains unavailable until Ollama actually serves K3, then becomes eligible as Hermes' native main model without borrowing the Kimi CLI session.
4. **Monitoring target:** July 27 is the first high-signal refresh date, plus any Ollama announcement or registry entry before then.

## Primary sources

- Moonshot official launch post: https://www.kimi.com/blog/kimi-k3
- Hermes upstream merged K3 catalog and live Nous verification: https://github.com/NousResearch/hermes-agent/pull/65913
- Hermes K3 transport hardening still under review (relevant only to direct Kimi coding endpoints, not the allowed Nous/Ollama routes): https://github.com/NousResearch/hermes-agent/pull/66303
- Ollama's public Kimi registry search (older Kimi releases, not K3): https://ollama.com/search?q=Kimi
- Open Ollama Cloud K3 request with no stated ETA: https://github.com/ollama/ollama/issues/17235
