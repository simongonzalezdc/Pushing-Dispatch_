# Provider and Executor Matrix

The committed `dispatch_matrix.toml` in the canonical Forgejo repository is the
fleet-wide machine-readable source of truth. Do not infer a
model from the harness name, and do not restore a retired lane from an old doc.

## Current Matrix

| Executor | Harness / access | Model | Vision | Intended role |
|---|---|---|---|---|
| `codex-luna` | Codex CLI, ChatGPT subscription | GPT-5.6 Luna (xhigh) | Yes | First attempt for every task |
| `codex-terra` | Codex CLI, ChatGPT subscription | GPT-5.6 Terra (high) | Yes | Explicit fallback after an unusable Luna result |
| `codex-sol` | Codex CLI, ChatGPT subscription | GPT-5.6 Sol (low default; high ceiling) | Yes | Exceptional fallback; explicitly escalate low → medium → high |
| `zai-glm` | Claude Code harness via `claude-glm52` | GLM 5.2 | **No** | Strong non-visual worker |
| `kimi-k27` | Native `kimi-cli` only | `kimi-code/kimi-for-coding` (Kimi K2.7) | Yes | Long context and implementation |
| `minimax-m3` | GJC backup path | `minimax-code/minimax-m3` | No | Backup coding lane |
| `agy-gemini-pro` | AGY only | Gemini 3.1 Pro (High) | Yes | Deep/visual Gemini lane |
| `agy-gemini-flash` | AGY only | Gemini 3.5 Flash (Medium) | Yes | Fast/visual Gemini lane |
| `kilo-free-auto` | Native Kilo CLI | `kilo/kilo-auto/free` | No | Free overflow only |
| `lm-studio` | Local LM Studio | `qwen3.6-35b-a3b-mtp` | No | Local/private fallback |

## Routing Rules

- Luna handles trivial mechanical work.
- Luna xhigh is the normal first attempt. Terra high is the explicit fallback after an unusable Luna result.
- Sol handles hard implementation, architecture, review, and consult work.
- Kimi K2.7 is available only through native Kimi CLI.
- Gemini is available only through AGY; Gemini CLI and direct-API wrappers are retired.
- MiniMax M3 is accessed through GJC as a backup.
- Kilo is free-only. Its safe default is `kilo/kilo-auto/free`; monthly named free models must be verified live before use. Never silently fall through to a paid Kilo model.
- GLM 5.2 has no vision. Image, screenshot, PDF-render, and visual tasks must use a vision-capable lane.
- When native search is missing or unreliable, use the globally configured DuckDuckGo `ddg` MCP. Never fabricate search results.

## Claude Code Means GLM 5.2 Here

The official Anthropic subscription is not an active provider lane. The global
`claude` entry point is a GLM 5.2 harness, backed by `bin/claude-glm52`; the
original binary remains available as `claude-real` for maintenance only.
Opus, Sonnet, and Haiku are not Dispatch executors.

## Authentication

- Codex executors use the logged-in ChatGPT subscription session, not an OpenAI API key.
- `zai-glm` uses `Z_AI_API_KEY` or the corresponding macOS Keychain / `pass` entry.
- Kimi, AGY, GJC, Kilo, and LM Studio use their native harness authentication.
- Do not paste credentials into the matrix or documentation.

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
