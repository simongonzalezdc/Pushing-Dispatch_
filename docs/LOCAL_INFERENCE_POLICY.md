# Local inference admission and routing policy

## Scope and authority

This policy is fleet-wide. It applies to **every task currently performed by a
cloud model**, not only Factory work. Factory, Hermes, Kyanite, interactive
work, writing, research, operations, coding, review, and future consumers all
receive local models through Pushing Dispatch after task-specific admission.

Pushing Dispatch owns model selection. Callers request a capability and must
not hard-code a host, serving product, or model because a model happens to be
installed. A locally reachable endpoint is capacity, not proof that it is good
enough for a task.

The Qwen assignments below are the operator's **working routing hypotheses**.
They are not promoted routes until the benchmark and acceptance rules in this
document prove additive value against the cloud model that currently performs
the work.

## Do not conflate the layers

| Layer | Examples | Decision it answers |
|---|---|---|
| Consumer | Factory, Dispatch, Open WebUI, Hermes, Personal LLM, Kyanite tools | Who requests inference? |
| Router | Pushing Dispatch, Factory OpenAI-compatible router | Which admitted endpoint gets the task? |
| Serving runtime | Unsloth Studio, llama.cpp, Ollama, LM Studio, ComfyUI | What loads and executes the weights? |
| Model artifact | Qwen3.5/3.6, Q4/Q6, image/video checkpoints | What capability and precision are evaluated? |

Unsloth is not a wholesale replacement for every layer. The current Unsloth
text service uses its bundled llama.cpp backend. Its image and video artifacts
still need a diffusion runtime or workflow engine such as ComfyUI,
stable-diffusion.cpp, Diffusers, or an LTX pipeline.

## Current fleet evidence snapshot

Observed on the NUCBox and Dell through 2026-07-23. This is dated evidence, not a static
routing matrix; re-probe before migration or deletion.

| Surface | Current evidence | Classification |
|---|---|---|
| Unsloth Studio and authenticated OpenAI proxy | Disabled after duplicate residency caused a CPU thermal-limit reset | Retained software, not an active serving path |
| Factory OpenAI-compatible router | Active and completing recurring requests through Unsloth | Proven active consumer path |
| Dedicated Unsloth Qwen 27B endpoint | Active with watchdog; exact Qwen 3.6 27B identity and 16,384 context | Resident coding/review and Dell-validation lane |
| Host Ollama plus tailnet proxy | Active; Open WebUI polls it and recent chat/generate requests exist | Still consumed; do not remove yet |
| Open WebUI | Configured for host Ollama and old llama.cpp endpoints | Proven Ollama consumer with stale endpoint debt |
| LM Studio daemon | No live LM Studio server observed | The legacy `lm-studio` executor is disabled and absent from automatic routing |
| Standalone llama.cpp system services | Legacy Qwen, Gemma, and embedding units are installed but inactive or failed | Retire only after dependency and rollback review |
| Personal LLM llama.cpp judge | Dedicated unit exists but was inactive at inspection | Specialized retained path until its experiment owner retires or migrates it |
| ComfyUI | Active image/video container with a large model library | Separate media runtime; retain |

Known configured consumers and adapters are:

- Factory through its local OpenAI-compatible endpoint.
- Pushing Dispatch through the compatibility `lm-studio` lane, the dedicated
  `unsloth-nucbox` lane, and a separate XPS Ollama GPU lane.
- Open WebUI through NUCBox Ollama.
- Tailnet Ollama clients, including Kyanite code that defaults to the NUCBox
  endpoint. The socket proxy hides original client attribution, so configuration
  proves eligibility but not recent use.
- Hermes' Ollama-local and Ollama Cloud provider integrations.
- Personal LLM's offline pairwise judge through a dedicated llama.cpp service.
- Elixis and other workspace tools with optional Ollama/OpenAI-compatible
  adapters. An adapter in source code is not an active dependency until runtime
  telemetry proves it.

## Current admitted local workcells

### Sticky resident (primary local coding leaf) — 2026-07-28

- **NUC Ornith (`unsloth-nucbox`):** `SC117/Ornith-1.0-35B-MTP-APEX-GGUF` APEX-I-Compact on Unsloth Studio proxy **`:8890`**, context **32768**, MTP n=2, sampling force 0.6/0.95/20/presence 0.
- **Admission:** m3-class only — bounded · localized · reversible · verifying. Leaf seat only (no breakout-top). Never sole architect/critic/security/vision/web.
- **Cloud YES/NO card (owning source):** `launchpad/docs/agents/ORNITH-GUIDELINES.md` § Cloud-orchestrator card  
- **Dispatch pack:** `includes: ornith-leaf` · `docs/ORCHESTRATING.md`  
- **Ops README:** `ops/unsloth-nucbox/README.md`  
- **Serialize:** one `unsloth-nucbox` job at a time (`parallel=1`); maxTokens leaf default **4096**  
- **Health:** `ssh nucbox '~/unsloth-ops/bin/ornith-workhorse-verify.sh'` (expect fail=0)  
- **Retired for dual-load:** dedicated agent **`:8892`** and on-demand workcells that activate via `:8892` remain unavailable while Ornith is the single big resident model.

### Legacy / specialized (dated; re-probe)


- **Dell:** `qwen35-2b-max:latest`, Qwen 3.5 2.3B Q8_0 (digest
  `9a75dfdd0b50ec88580606948ca9364902a4b5cdf5df465161852f4f64f1df2c`),
  65,536 configured context. Use only for tiny exact/mechanical work, and
  always gate its output through resident NUC validation.
- **NUC general:** Qwen 3.5 35B-A3B Q4_K_M, 32,768 context and 2,048-token
  generation cap, bounded general work.
- **NUC review:** Qwen 3.5 27B Q4_K_M, 32,768 context, 1,536-token generation
  cap, read-only tool admission, and a 22,000-token measured tool-loop reserve
  for independent general review.
- **NUC coding:** Qwen 3.6 35B-A3B, 32,768 context, 1,024-token generation cap,
  and 8-thread inference/batch caps for small isolated coding edits. Dispatch
  reserves 22,000 tokens for measured agent/tool-loop growth before residency.
- **NUC resident:** Qwen 3.6 27B Q4_K_M, 16,384 context, coding/review and Dell
  validation.

The proven Qwen task classes are admitted to automatic routing with
deterministic ceilings: bounded general work to Qwen 3.5 35B under 24K input
tokens, bounded review to Qwen 3.5 27B under 5K, and bounded coding to Qwen 3.6
35B under 5K. Broad/risky scope is evaluated before mechanical keywords, so it
cannot fall into the Dell lane. Oversized, visual, long-context, breakout, and
consult work retains the existing non-local tier. Economics remains deferred
and unproven; this is scoped work admission, not blanket model promotion.

All NUC inference runs at the hardware-enforced `low` GPU performance level.
The controller rejects activation above 85°C, and an independent runtime guard
stops and restores any workcell that reaches 90°C or loses its Tctl sensor.
The resident Qwen 3.6 27B service applies the same power cap at every start.

## Qwen working hypotheses: eight primary candidates

The family, architecture, and quantization axes must be tested independently.
The same family name does not make two architectures or quants interchangeable.

| Family | Architecture | Quant | Candidate role before admission |
|---|---|---|---|
| Qwen3.5 | 35B-A3B MoE | Q4 | Fast general-purpose / co-work candidate |
| Qwen3.5 | 35B-A3B MoE | Q6 | Higher-fidelity fast general-purpose candidate |
| Qwen3.5 | 27B dense | Q4 | Quality-first general-purpose candidate with lower memory cost |
| Qwen3.5 | 27B dense | Q6 | Highest-quality general-purpose candidate |
| Qwen3.6 | 35B-A3B MoE | Q4 | Fast coding candidate |
| Qwen3.6 | 35B-A3B MoE | Q6 | Higher-fidelity fast coding candidate |
| Qwen3.6 | 27B dense | Q4 | Quality-first coding candidate with lower memory cost |
| Qwen3.6 | 27B dense | Q6 | Highest-quality coding candidate |

The intended family split is:

- **Qwen3.5:** general-purpose, non-coding work analogous to a Claude
  co-work session: writing, research synthesis, planning, operations,
  extraction, analysis, and tool-mediated office work.
- **Qwen3.6:** coding-specialist work: implementation, debugging, code review,
  test design, refactoring, and repository tool use.
- **35B-A3B MoE:** expected to be faster with slightly lower quality.
- **27B dense:** expected to give the strongest results but run more slowly.
  The current operator observation is about 18 tokens/second; every benchmark
  receipt must remeasure it rather than treating that number as permanent.
- **Q4 versus Q6:** Q4 is the resource/speed candidate and Q6 is the
  quality-retention candidate. Neither wins by assumption.

These are hypotheses to test, not permission to route all general work to 3.5
or all coding work to 3.6. Promotion is per task class and role.

## Required benchmark program

### Test matrix

Run all eight candidates on the same pinned hardware generation and serving
runtime. Then, for finalists, run a serving-runtime comparison using the same
model artifact where formats permit. This separates model quality from Unsloth,
Ollama, LM Studio, or standalone llama.cpp overhead.

The task corpus must include real, redacted examples from:

- general co-work, drafting, rewriting, research synthesis, planning, and
  operations;
- structured extraction, JSON/schema compliance, classification, and long
  context;
- tool selection, tool argument accuracy, recovery from tool failure, and
  multi-step completion;
- coding implementation, debugging, test creation, refactoring, code review,
  and repository navigation;
- builder, reviewer, and verifier roles where those roles materially differ.

Every task class keeps its current cloud route as the control. Use paired blind
evaluation, identical inputs and tool permissions, at least three repeated runs
per case, pinned sampling settings, exact model and artifact digests, and both
cold and warm measurements.

### Record both usefulness and cost

Each result records:

- task success and rubric score;
- factual and code correctness;
- tool-call selection, arguments, and completion rate;
- structured-output validity and unsupported-claim rate;
- independent reviewer/verifier result;
- time to first token, generation tokens/second, total wall time, and timeout
  rate;
- RAM/VRAM, disk, energy where available, and maximum safe concurrency;
- quality under short, medium, and long context;
- serving runtime, runtime version, model digest, quant, prompt digest, and
  hardware generation.

### Admission and retirement rules

1. Admit a model only for the exact task class and role where it is measurably
   non-inferior or better than the existing cloud control at an acceptable
   latency and reliability cost.
2. A faster result is not additive if it produces more repair work. A prettier
   answer is not additive if tools, facts, or verification fail.
3. Keep separate builder, reviewer, and verifier decisions. Do not let a model
   judge its own promotion.
4. A Q4 win does not admit Q6, a dense win does not admit MoE, and a coding win
   does not admit general-purpose work.
5. Publish an evidence receipt and a rollback target for every route change.
6. Unproven variants remain disabled. Negative findings are retained rather
   than reinterpreted as success.
7. Re-run the affected cells after model, quant, runtime, driver, prompt,
   context, or hardware changes.

## Image and video

Unsloth has useful media solutions, but the clean architecture is **Unsloth
artifacts plus a media runtime**, not “replace ComfyUI with Unsloth.”

- Image: Unsloth publishes Dynamic GGUF and 4-bit Qwen-Image variants and
  documents ComfyUI, Diffusers, and stable-diffusion.cpp inference.
- Video: Unsloth publishes LTX-2.3 GGUF variants for text/image/video and
  synchronized audio-video workflows. The documented local execution path uses
  ComfyUI/LTX nodes or the LTX PyTorch pipeline.
- Vision fine-tuning is a different capability: it trains models to understand
  images and must not be described as image generation.

Media models need their own benchmark grid: prompt adherence, visual quality,
identity/reference preservation, text rendering, temporal consistency, audio
sync, generation time, peak memory, disk footprint, and human preference.

Official references:

- https://unsloth.ai/docs/models/tutorials/qwen-image-2512
- https://unsloth.ai/docs/models/tutorials/qwen-image-2512/stable-diffusion.cpp
- https://huggingface.co/unsloth/LTX-2.3-GGUF
- https://unsloth.ai/docs/basics/vision-fine-tuning

## Consolidation guardrails

1. Do not remove Ollama while Open WebUI, tailnet clients, Hermes, or any
   small-model/embedding workflows still depend on its native API.
2. Do not remove llama.cpp wholesale: Unsloth currently uses a bundled
   llama.cpp backend, and specialized standalone services may still need it.
3. On-demand standalone model units must remain disabled between requests;
   inactive-but-enabled is not a restored state because systemd can start them
   beside the resident lane after a reboot. Reclaim their weights only after a
   boot test, dependency scan, rollback receipt, and observation window.
4. LM Studio assets are removable only after proving there is no live daemon,
   no unique model artifact, and no consumer that cannot use the canonical
   OpenAI-compatible endpoint. Rename the compatibility executor separately so
   configuration does not imply that LM Studio is running.
5. Keep the resident Qwen 3.6 27B endpoint and watchdog as the restoration
   target until a separately canaried consolidation proves equivalent Dell
   validation and bounded agentic behavior.
6. Keep ComfyUI and its media library until an alternative passes image and
   video workflow parity; text-serving consolidation is not media migration.
7. One model has one canonical fleet home unless a measured latency,
   availability, or isolation requirement justifies a second copy.
8. Reclaim storage from proven duplicates, never from a directory merely
   because another product can theoretically load the same model family.
