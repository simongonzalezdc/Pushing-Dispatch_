---
name: pushing-dispatch
description: Route delegated, background, parallel, consultation, coding, research, or specialist work through the fleet's canonical Pushing Dispatch matrix.
---

# Pushing Dispatch for Liam

Pushing Dispatch is the model-selection front door. Hermes remains Liam's resident orchestrator; Dispatch selects and launches external specialist workers.

## Required behavior

- Before external delegation, run `hermes-dispatch route --mode task --task "<brief>"`.
- Launch task workers with `hermes-dispatch start --mode task --task "<brief>" --cwd "$PWD"`.
- Launch isolated breakout workers with `hermes-dispatch start --mode breakout --task "<brief>" --cwd "$PWD"`.
- Use `hermes-dispatch route --mode consult --task "<brief>"` for consultations.
- Use `hermes-dispatch status <worker-id>` and `hermes-dispatch list --active` to monitor workers.
- Do not hand-pick models when Dispatch is available.
- Hermes-native children inherit GLM 5.2 and are only for tightly coupled in-session decomposition. They are not the external provider-selection layer.

## Canonical lanes

- Kimi subscription: Kimi K3 through the external `kimi-k3-cli` Dispatch lane only; never as a native Hermes HTTP provider.
- Ollama Cloud: separate `kimi-k3-ollama` lane, live-catalog gated. This is the only K3 access path Hermes may promote to its native main model.
- Z.AI: GLM 5.2, text-only.
- GJC: MiniMax M3 and backup GLM.
- Grok Build: `grok-build` through xAI's official `grok` CLI, pinned to `grok-4.5`, vision-capable, and preferred for retired Claude Opus-class hard implementation, architecture, adversarial review, breakout, and consult work.
- Codex subscription: GPT-5.6 Luna, Terra, and Sol.
- AGY: Gemini Flash and Pro.
- Kilo: free-auto/currently free models only.
- LM Studio: local fallback.

Vision must use a vision-capable lane, never GLM. Weak or failed search uses DuckDuckGo MCP. Claude Code always targets Z.AI GLM 5.2 and never an Anthropic subscription.

The committed matrix under `$HOME/.local/share/pushing-dispatch/repo` is authoritative. Run `hermes-dispatch doctor` for host-specific availability.
