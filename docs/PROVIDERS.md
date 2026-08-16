# Provider and Executor Matrix

The committed `dispatch_matrix.toml` in the canonical Forgejo repository is the
fleet-wide machine-readable source of truth. Do not infer a
model from the harness name, and do not restore a retired lane from an old doc.

## Current Matrix

| Executor | Harness / access | Model | Vision | Intended role |
|---|---|---|---|---|
| `codex-luna` | Codex CLI, ChatGPT subscription | GPT-5.6 Luna (xhigh) | Yes | First attempt for ordinary work |
| `codex-terra` | Codex CLI, ChatGPT subscription | GPT-5.6 Terra (high) | Yes | Explicit fallback after an unusable Luna result |
| `codex-sol` | Codex CLI, ChatGPT subscription | GPT-5.6 Sol (low default; high ceiling) | Yes | Exceptional fallback; explicitly escalate low → medium → high |
| `grok-build` | Official Grok CLI | Grok 4.6 (`grok-4.6`) | Yes | Claude Opus-class replacement |
| `zai-glm` | **Canonical call: ZCode `zcode -p`.** Executor still launches legacy `claude-glm52` until rewired | GLM 5.3 | Prefer dedicated vision lanes | Strong coding worker |
| `kimi-k3-cli` | Official Kimi CLI, Kimi subscription | `kimi-code/k3` (Kimi K3) | Yes | Primary 1M-context K3 subscription lane |
| `kimi-k3-ollama` | Ollama Cloud only | `kimi-k3` (Kimi K3) | Yes | Live-gated Ollama route and future Hermes main model |
| `minimax-m3` | GJC backup path | `minimax-code/minimax-m3` | No | Backup coding lane |
| `agy-gemini-flash` | AGY only | Gemini 3.5 Flash (Medium) | Yes | Fast/visual Gemini lane |
| `kilo-free-auto` | Native Kilo CLI | `kilo/kilo-auto/free` | No | Free overflow only |
| `ollama-xps-gpu` | Dell Ollama plus resident-NUC validator | Qwen 3.5 2.3B Q8_0 | No | Tiny mechanical work; validation required |
| `unsloth-nucbox` | Resident NUC Unsloth `:8890` | Ornith-1.0-35B MTP APEX | No | Sticky m3-class coding leaf, 32,768 context; progressive skills |
| `qwen35-35b-general` | On-demand NUC llama.cpp | Qwen 3.5 35B-A3B Q4_K_M | No | Auto-routed bounded general work, 32,768 context |
| `qwen35-27b-review` | On-demand NUC llama.cpp | Qwen 3.5 27B Q4_K_M | No | Auto-routed bounded independent review, 32,768 context, read-only tool admission, and a 512-token answer cap |
| `qwen36-35b-coding` | On-demand NUC llama.cpp | Qwen 3.6 35B-A3B Q4_K_M | No | Auto-routed bounded coding work, 32,768 context with 8-thread thermal cap |

## Routing Rules

- Unclassified standard work currently starts with `zai-glm`; local task-family
  tiers are evaluated first when deterministic signals match. Within the Codex
  fallback ladder, Luna precedes Terra and Sol.
- Grok 4.6 replaces retired Claude Opus-class work. Hard implementation, deep architecture, adversarial review, breakout, and consult tiers prefer `grok-build`.
- Sol is an exceptional Codex fallback only: escalate low, medium, then high and stop after high.
- Kimi subscription access always uses `kimi-k3-cli` through the official Kimi CLI. Ollama access always uses `kimi-k3-ollama`, remains unroutable until the live catalog exposes `kimi-k3`, and is the only K3 lane eligible to run natively inside Hermes. Credentials never cross between lanes.
- Gemini is available only through AGY; Gemini CLI and direct-API wrappers are retired.
- MiniMax M3 is accessed through GJC as a backup.
- Kilo is free-only. Its safe default is `kilo/kilo-auto/free`; monthly named free models must be verified live before use. Never silently fall through to a paid Kilo model.
- Call GLM through ZCode (`zcode -p`), not Claude Code. See `docs/ZCODE.md`.
- Do not default visual-QA / screenshot work to GLM/ZCode. Prefer a dedicated vision lane unless the user named GLM for eyes.
- When native search is missing or unreliable, use the globally configured DuckDuckGo `ddg` MCP. Never fabricate search results.
- Atomic mechanical work routes to the Dell only when the brief is genuinely
  narrow; repository-wide, multi-file, risky, architectural, migration, and
  security-sensitive signals escalate before the mechanical keyword check.
- Bounded general, review, and coding briefs route respectively to
  `qwen35-35b-general`, `qwen35-27b-review`, and `qwen36-35b-coding`.
  Deterministic input ceilings are 24K, 5K, and 5K tokens. Oversized work
  returns to the standard/long-context tiers instead of overflowing a local
  serving slot.
- Automatic local admission is task-class scoped, not blanket model promotion.
  Breakout, consult, hard/risky, visual, and long-context tiers are unchanged.
  Economics remains deferred and unproven.

## Local Qwen NUC Safety

Only one model is resident at a time. Studio and proxy are disabled. GPU performance level is low. Preflight rejects Tctl above 85°C. Runtime guard stops at 90°C. Every on-demand request must restore the resident qwen27 plus watchdog and leave all on-demand targets inactive and disabled.

## GLM is ZCode here

The official Anthropic subscription is not an active provider lane. **Agents
call GLM through ZCode** (`zcode -p`). Opus, Sonnet, and Haiku are not
Dispatch executors.

The global `claude` → `bin/claude-glm52` symlink is **legacy** for the
`zai-glm` executor only. `claude-real` remains the stock Claude Code binary
for harness maintenance. Do not teach `claude -p` as the GLM path.

## Authentication

- Codex executors use the logged-in ChatGPT subscription session, not an OpenAI API key.
- `zai-glm` uses `Z_AI_API_KEY` or the corresponding macOS Keychain / `pass` entry.
- Grok uses the official CLI's browser/OAuth session or `XAI_API_KEY`.
- Kimi, AGY, GJC, Kilo, and LM Studio use their native harness authentication.
- Do not paste credentials into the matrix or documentation.

### Grok Build

Install the official xAI CLI with `npm install -g @xai-official/grok`, then run
`grok login --oauth` (or `grok login --device-auth` on a headless host). Confirm
the session with `grok models`; run plain `grok` to open the interactive TUI or
`grok -p "Explain this repo"` for one-shot use. The active executor pins `grok-4.6`. Dispatch
requires both the `grok` binary and either its OAuth auth file or `XAI_API_KEY`
before treating the lane as available. The wrapper uses `--prompt-file` for
large briefs and applies `workspace` or `read-only` sandbox profiles by mode.

## Verify Current State

```bash
pushing-dispatch validate-matrix dispatch_matrix.toml
pushing-dispatch doctor
pushing-dispatch doctor --probe
```

The full probe must pass through each real wrapper before the matrix is called
green. Route a task through `auto`; do not hand-pick a provider from this table.

## Retired Lanes

GPT-5.5, Codex OSS, NUCBox Gemma, direct Anthropic subscription models,
Moonshot Anthropic-compatible Kimi, DeepSeek, direct MiniMax, Gemini CLI, and
legacy direct Gemini API lanes are retired. Historical handoffs and plans may
mention them, but they are not operational instructions.
