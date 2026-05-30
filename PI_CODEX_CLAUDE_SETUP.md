# Pushing Dispatch Local Setup

This checkout is configured for mixed Claude Code, Codex, metered provider, and Raspberry Pi/local-model use.

## Executors

| Executor | CLI path | Use for |
| --- | --- | --- |
| `opus`, `sonnet`, `haiku` | Claude Code | Anthropic / Claude Code workers |
| `kimi-coding` | Claude Code via Kimi Coding Anthropic-compatible endpoint | Manifest Kimi Coding lane |
| `kimi-moonshot` | Claude Code via Moonshot/Kimi Anthropic-compatible endpoint | Legacy Kimi/Moonshot lane |
| `deepseek` | Claude Code via DeepSeek Anthropic-compatible endpoint | Direct DeepSeek code lane |
| `zai-glm`, `zai-air` | Claude Code via Z.ai Anthropic-compatible endpoint | Manifest GLM reasoning and fast-edit lanes |
| `minimax`, `minimax-m25`, `minimax-m25-highspeed` | Claude Code via MiniMax Anthropic-compatible endpoint | Manifest/Goose MiniMax lanes |
| `minimax-coding-plan` | MiniMax OpenAI-compatible endpoint | Goose custom MiniMax coding-plan lane |
| `inception-mercury` | Inception Labs OpenAI-compatible endpoint | Goose custom Mercury-2 lane |
| `lm-studio` | LM Studio OpenAI-compatible endpoint over Tailscale | Pi/Mac/local model lane |
| `gemini-pro`, `gemini-flash`, `gemini-lite` | Google Gemini API-key generateContent | Gemini pro/flash/lite effort lanes |
| `kilo-deepseek-high`, `kilo-qwen-high`, `kilo-mistral-medium`, `kilo-research`, `kilo-free` | Kilo Gateway OpenAI-compatible API | Kilo reasoning, research, and cheap lanes |
| `codex` | Codex CLI | OpenAI/Codex workers |
| `openai-gpt55`, `openai-gpt55-high`, `openai-gpt55-xhigh`, `openai-mini`, `codex-spark` | Codex CLI with pinned models/effort | Manifest OpenAI subscription lanes |
| `codex-oss` | Codex CLI with `--oss --local-provider ollama` | Raspberry Pi or other local Ollama workers |

## Mac Setup

Install the shared global routing commands:

```bash
bash bin/install-global-routing.sh
pushing-dispatch route --mode task --task "fix a typo"
```

Verify tools:

```bash
bash bin/check-prereqs.sh
python3 cli.py validate-matrix dispatch_matrix.toml
```

Claude Code workers use Claude Code login or `ANTHROPIC_API_KEY`.

Codex workers use Codex login/config or `OPENAI_API_KEY`:

```bash
codex login
codex doctor
```

Manifest-compatible third-party workers read API keys in this order:

1. Environment variable, such as `KIMI_API_KEY`, `MOONSHOT_API_KEY`, `DEEPSEEK_API_KEY`, `MINIMAX_API_KEY`, `CUSTOM_MINIMAX_CODING_PLAN_API_KEY`, `CUSTOM_INCEPTION_API_KEY`, `Z_AI_API_KEY`, `KILO_API_KEY`, or `GEMINI_API_KEY`.
2. macOS Keychain: service `pushing-dispatch`, account `<provider>_api_key`.
3. `pass`: `pushing-dispatch/<provider>_api_key`.

## Raspberry Pi / Local Ollama Setup

Install the same repo on the Pi, plus:

```bash
python3 --version
bash --version
git --version
codex --version
ollama --version
```

Pull a local model on the Pi:

```bash
ollama pull qwen2.5-coder:7b
```

Run a local Codex worker with:

```bash
export CODEX_LOCAL_PROVIDER=ollama
export CODEX_MODEL=qwen2.5-coder:7b
pushing-dispatch task start \
  --executor auto \
  --task "Respond with exactly: Status: DONE" \
  --cwd "$(pwd)" \
  --slug pi-smoke
```

Then check:

```bash
python3 cli.py list --active
python3 cli.py status <worker-id>
```

## Useful Overrides

```bash
export CODEX_MODEL=gpt-5.5
export CODEX_SANDBOX=workspace-write
export CODEX_APPROVAL_POLICY=never
export DISPATCH_ROOT="$HOME/.local/share/pushing-dispatch"
export MOONSHOT_API_KEY=...
export DEEPSEEK_API_KEY=...
export CUSTOM_INCEPTION_API_KEY=...
export CUSTOM_MINIMAX_CODING_PLAN_API_KEY=...
```

Manifest's OpenAI account labels (`Personal`, `PuenteWorks`, `CERAFICA`) live in
Manifest subscription state. Pushing Dispatch pins the same models through Codex
CLI; which account pays/runs depends on the active Codex CLI login/profile.

For read-only Codex consults, pass `--read-only` to the wrapper or keep the task in `consult` mode.
