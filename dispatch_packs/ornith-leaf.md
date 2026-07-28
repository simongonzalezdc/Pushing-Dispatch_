# Ornith leaf (cloud → NUC admission pack)

**Owning source (do not fork full policy):**  
`launchpad/docs/agents/ORNITH-GUIDELINES.md` § *Cloud-orchestrator card*

## One-liner

Ornith (`unsloth-nucbox`) = free sticky NUC leaf for **bounded · localized · reversible · verifying** local coding/ops with tools and proof. Never sole architect, critic, security, vision, web, breakout-top, or long-context. **Serialize** jobs (one at a time).

## Admit only if all four pass

1. **Bounded** — single file/symbol or mechanical sweep  
2. **Localized** — no public API / migrations / auth / payments / cross-module seams  
3. **Reversible** — failure leaves no systemic damage  
4. **Verifying** — same job ends with a real proof command/test  

## YES examples

- One-file fix / implement with focused test  
- RED→GREEN pytest repair  
- Local ops: health verify, media import check, Signal measure collector  
- Sliced m3 leaf from a larger cloud campaign  

## NO examples

- Architect / ralplan consensus → GLM  
- Independent PR review → GLM (reviewer ≠ author)  
- Security / auth / migrations → GLM  
- Vision / screenshots → AGY Gemini  
- Web search → Gemini / DDG  
- Hard multi-module / breakout top → `grok-build` / Codex  
- Typos / free overflow → `kilo-free-auto`  

## Handoff

```bash
pushing-dispatch route --mode task --task "local coding: <goal + acceptance>"
# or:
pushing-dispatch task start --executor unsloth-nucbox --cwd "$PWD" \
  --task "Goal: … Paths: … Acceptance: <cmd>. Status: DONE"
```

Briefs may `includes: ornith-leaf` so workers/orchestrators see this card without loading the full fleet guidelines body.

## Ops

- Health: `ssh nucbox '~/unsloth-ops/bin/ornith-workhorse-verify.sh'` → `fail=0`  
- Do not fan out multiple concurrent `unsloth-nucbox` workers  
- Leaf seat only (`hard_wall_block_breakout_top`)  
