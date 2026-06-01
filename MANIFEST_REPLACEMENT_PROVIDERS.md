# Manifest Replacement Provider Map

Pushing Dispatch now mirrors the local Manifest routing matrix directly instead
of using Manifest as a gateway.

Source of truth inspected:

- `/Users/simongonzalezdecruz/Documents/Codex/2026-05-23/mnfst-manifest-https-github-com-mnfst/manifest/ops/manifest-routing/matrix.json`

## Ported Providers

| Manifest provider | Manifest model(s) | Pushing Dispatch executor(s) | Key source |
| --- | --- | --- | --- |
| `openai` subscription | `gpt-5.5` | `openai-gpt55` | Codex CLI login/config |
| `openai` subscription | `gpt-5.5` high/xhigh | `openai-gpt55-high`, `openai-gpt55-xhigh` | Codex CLI login/config |
| `openai` subscription | `gpt-5.4-mini` | `openai-mini` | Codex CLI login/config |
| `openai` subscription | `gpt-5.3-codex-spark` | `codex-spark` | Codex CLI login/config |
| `anthropic` subscription | `claude-opus-4-8` | `opus` | Claude Code login/config |
| `anthropic` subscription | `claude-sonnet-4-6` | `sonnet` | Claude Code login/config |
| `anthropic` subscription | `claude-haiku-4-5-20251001` | `haiku` | Claude Code login/config |
| Kimi custom provider | `kimi-for-coding` | `kimi-coding` | `KIMI_API_KEY` |
| Moonshot/Kimi provider | `kimi-k2.6` | `kimi-moonshot` | `MOONSHOT_API_KEY` |
| DeepSeek provider | `deepseek-v4-flash` | `deepseek` | `DEEPSEEK_API_KEY` |
| Z.ai / GLM custom provider | `glm-5.1` | `zai-glm` | `Z_AI_API_KEY` |
| Z.ai / GLM custom provider | `glm-4.5-air` | `zai-air` | `Z_AI_API_KEY` |
| MiniMax subscription lane | `MiniMax-M3` | `minimax` | `MINIMAX_API_KEY` |
| MiniMax coding plan | `MiniMax-M2.5` | `minimax-m25` | `MINIMAX_API_KEY` |
| MiniMax coding plan | `MiniMax-M2.5-highspeed` | `minimax-m25-highspeed` | `MINIMAX_API_KEY` |
| MiniMax custom OpenAI-compatible plan | `MiniMax-M2.5` | `minimax-coding-plan` | `CUSTOM_MINIMAX_CODING_PLAN_API_KEY` |
| Inception Labs custom provider | `Mercury-2` | `inception-mercury` | `CUSTOM_INCEPTION_API_KEY` |
| LM Studio over Tailscale | `qwen3-coder-next-reap-40b-a3b-i1` | `lm-studio` | `OPENAI_API_KEY` |
| Gemini API-key lane | `gemini-3.1-pro-preview` | `gemini-pro` | `GEMINI_API_KEY` or `GOOGLE_API_KEY` |
| Gemini API-key lane | `gemini-3-flash-preview` | `gemini-flash` | `GEMINI_API_KEY` or `GOOGLE_API_KEY` |
| Gemini API-key lane | `gemini-3.1-flash-lite-preview` | `gemini-lite` | `GEMINI_API_KEY` or `GOOGLE_API_KEY` |
| Kilo Gateway | `deepseek/deepseek-v4-pro` high | `kilo-deepseek-high` | `KILO_API_KEY` |
| Kilo Gateway | `qwen/qwen3.7-max` high | `kilo-qwen-high` | `KILO_API_KEY` |
| Kilo Gateway | `mistralai/mistral-medium-3-5` medium | `kilo-mistral-medium` | `KILO_API_KEY` |
| Kilo Gateway | `perplexity/sonar-pro-search` medium | `kilo-research` | `KILO_API_KEY` |
| Kilo Gateway | free/cheap route | `kilo-free` | `KILO_API_KEY` |
| Local OSS / Pi | local Ollama model | `codex-oss` | Codex CLI + Ollama |

## What Changed

- Kimi is no longer the old Moonshot wrapper. Manifest's Kimi Coding lane uses
  `https://api.kimi.com/coding`, model `kimi-for-coding`, and `KIMI_API_KEY`.
- Moonshot/Kimi and direct DeepSeek are routable again as `kimi-moonshot` and
  `deepseek`, instead of being orphaned wrapper scripts.
- Z.ai is now first-class through `https://api.z.ai/api/anthropic`.
- MiniMax is now first-class through `https://api.minimax.io/anthropic`.
- Goose/custom provider lanes are now first-class too: `inception-mercury`,
  `minimax-m25`, `minimax-m25-highspeed`, `minimax-coding-plan`, and
  `lm-studio`.
- OpenAI Manifest subscription lanes are represented as Codex CLI wrappers with
  pinned models.
- The auto-router now defaults breakout work to `openai-gpt55-high`, coding work
  to `codex-spark`, quick work to `openai-mini`, consults to Opus 4.8, and
  long-context work to `kimi-coding`.
- Expensive/deep reasoning variants are explicit executor names instead of hidden
  environment switches: `openai-gpt55-high`, `openai-gpt55-xhigh`,
  `zai-glm`, `gemini-pro`, `kilo-deepseek-high`, and `kilo-qwen-high`.

## Not Fully Portable Without More Auth Plumbing

- Manifest OpenAI account labels `Personal`, `PuenteWorks`, and `CERAFICA` are
  subscription account labels inside Manifest. Pushing Dispatch can select the
  model through Codex CLI, but account selection depends on Codex CLI's local
  login/profile state.
- Manifest Gemini Code Assist subscription lanes are OAuth/Code Assist lanes.
  Pushing Dispatch now has API-key Gemini wrappers; exact subscription-account
  reuse still requires a Code Assist OAuth bridge.
- Manifest Kilo API-key lanes are wired to Kilo Gateway. They need `KILO_API_KEY`
  exported or stored in Keychain before live execution.

Do not paste secrets into this repository. Use environment variables or the
existing keychain loader:

```bash
export KIMI_API_KEY=...
export MOONSHOT_API_KEY=...
export DEEPSEEK_API_KEY=...
export MINIMAX_API_KEY=...
export CUSTOM_MINIMAX_CODING_PLAN_API_KEY=...
export CUSTOM_INCEPTION_API_KEY=...
export Z_AI_API_KEY=...
export KILO_API_KEY=...
export GEMINI_API_KEY=...
```

Or store them in macOS Keychain under service `pushing-dispatch` with accounts
`kimi_api_key`, `moonshot_api_key`, `deepseek_api_key`, `minimax_api_key`,
`custom_minimax_coding_plan_api_key`, `custom_inception_api_key`, and
`z_ai_api_key`.
