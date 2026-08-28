# Provider and Executor Matrix

The committed `dispatch_matrix.toml` in the canonical Forgejo repository is the
fleet-wide machine-readable source of truth. Do not infer a
model from the harness name, and do not restore a retired lane from an old doc.

## Current Matrix

Provider truth as of **2026-08-27**, rebuilt from the 22 `[executors.*]`
stanzas in `dispatch_matrix.toml`.

| Executor | Pricing class | Harness / access | Model | Vision | Intended role |
|---|---|---|---|---|---|
| `kimi-k3-cli` (🟩 Kimi K3) | prepaid-yearly | Official Kimi CLI, OAuth session | `kimi-code/k3` (Kimi K3) | Yes (vision + video) | Survivor K3 subscription; 1M context; leads the long-context tier; steward for hard analysis / vision / long-doc review |
| `kimi-k3-key` (🟩 Kimi K3 Key) | prepaid-yearly | Kimi CLI, API-key account (`KIMI_API_KEY`) | `kimi-code/k3` | Yes | Second Kimi Code subscription |
| `kimi-k3-kyanite` (🟩 Kimi Kyanite) | prepaid-yearly | Kimi CLI, API-key account | `kimi-code/k3` | Yes | DYING subscription — routed first in every kimi-eligible tier to drain quota; prune once it hard-fails |
| `zai-glm` (🟡 GLM Z.ai) | prepaid-yearly | **ZCode `zcode -p`** (canonical) | GLM 5.3 (`glm-5.3`) | No — prefer dedicated vision lanes | Primary GLM worker; heads the standard / local / consult tiers |
| `zai-glm-flash` (⚡ GLM Flash) | prepaid-yearly | ZCode under isolated HOME (`~/.zcode/flash-home`), model pin enforced | `glm-5.3-flash` | No — same rule as `zai-glm` | GLM-5.3-Flash lane (added 2026-08-26); same Coding Plan quota as `zai-glm`, zero marginal cost |
| `minimax-m3` (🟥 MiniMax) | prepaid-yearly | GJC | `minimax-code/minimax-m3` | Yes (image and video, fleet-verified) | Prepaid backup; breakout/task only (no consult) |
| `codex-luna` (🔵 Luna) | scarce | Codex CLI, ChatGPT subscription | GPT-5.6 Luna (xhigh) | Yes | Explicit-only since 2026-08-24 — request by name, never auto-routed |
| `codex-terra` (🟠 Terra) | scarce | Codex CLI, ChatGPT subscription | GPT-5.6 Terra (high) | Yes | Explicit retry after an unusable Luna result; explicit-only |
| `codex-sol` (🟣 Sol) | scarce | Codex CLI, ChatGPT subscription | GPT-5.6 Sol (low) | Yes | Exceptional explicit fallback; escalate low → medium → high |
| `codex-sol-high` (🟣 Sol High) | scarce | Codex CLI, ChatGPT subscription | GPT-5.6 Sol (high) | Yes | Effort-split variant of `codex-sol` (effort-granularity doctrine) |
| `grok-build` (🟢 Grok) | scarce | Official Grok CLI | `grok-4.6` | Yes | Explicit-only since 2026-08-24; accounts end Sept 2026 wk1/wk2 — burn-down by direct request |
| `xiaomi-mimo` (🟣 MiMo) | subscription | Xiaomi MiMo OpenAI-compatible API; Keychain key `xiaomi_api_key`, `api-key` header | `mimo-v2.5-pro` (stanza aligned to wrapper default, eeee4cc) | No | Reactivated 2026-08-25 (CEO paid use-it month); amber until the fresh key is verified live |
| `agy-gemini-flash` (🟦 Gemini Flash) | free | AGY only | Gemini 3.7 Flash (Medium — medium-only per CEO 2026-08-22) | Yes | Workspace-included Gemini lane |
| `kilo-free-auto` (🩵 Kilo DS-Flash) | free | Native Kilo CLI | `kilo/kilo-auto/free` | No | Used only once Kilo account credits are exhausted; verify the rotating monthly `:free` model live before use |
| `dsh` (🐬 DSH) | credit | DeepSeek Harness headless (`~/.dsh/settings.yaml`) | `deepseek-v4-flash` | No | Flash-ONLY until CEO notice (Pro price hike); task/consult |
| `deepseek-v4-pro` (🐋 DeepSeek Pro) | credit | DeepSeek platform key (`api.deepseek.com`, preferred since 08-26) with Ollama Cloud fallback | `deepseek-v4-pro:0813` | No | Hard-tier / review-seat credit lane |
| `deepseek-v4-flash` (🐋 DeepSeek Flash) | credit | Ollama Cloud (`OLLAMA_API_KEY`) | `deepseek-v4-flash:0731` | No | Trivial/standard overflow credit lane |
| `lm-studio` (🧪 LM Studio) | local | LM Studio host `:4000` | `qwen3.5-35b-a3b` | No | `disabled = true` in the matrix |
| `ollama-xps-gpu` (🖥️ Ollama XPS) | local | Dell Ollama + resident-NUC validator | `qwen35-2b-max` | No | Tiny mechanical work; task mode only, validator-gated |
| `nucbox-champion` (🟤 Champion) | local | NUC llama-server via qwen27-forward `:46380` | `Qwen3.8-27B` | Yes (mmproj, 6/6 certified) | Local-first lead: default task/breakout executor; iterative agent loops (54x prompt cache), 262k context, think-off |
| `nucbox-ornith` (🟠 Ornith 35B) | local | NUC llama-server `:46381` | `Ornith-1.5-35B` | Yes (5/6 battery) | One-shot generation, math with thinking, long analysis; leads the hard-task tier |
| `command-code` (⬛ Command Code) | credit | commandcode.ai CLI, Pro plan session (authenticated as simongonzalezdc) | `deepseek/deepseek-v4-flash` | No | Prepaid credit pool for coding ($80 credits/mo, burn-down, never refilled); verified live 2026-08-24 |

## Routing Rules

- **Local-first doctrine (CEO 2026-08-24):** nucbox champion + ornith lead every
  auto-route tier they can carry; ornith (think-ON) leads pure reasoning
  (98.3% GSM8K); `command-code` is the prepaid credit pool for coding; the
  remaining prepaid lanes follow. Back-compat defaults: `default_task` and
  `default_breakout` = `nucbox-champion`, `default_consult` = `nucbox-ornith`.
- `codex-*` and `grok-build` are **explicit-only**: removed from every auto
  list; those accounts end Sept 2026 wk1/wk2 — burn-down by direct request only.
- Sol is an exceptional Codex fallback only: escalate low, medium, then high and stop after high.
- Kimi subscription access always uses `kimi-k3-cli` through the official Kimi CLI; `kimi-k3-kyanite` is routed first in kimi-eligible tiers to drain the dying sub. `kimi-k3-ollama` was attic'd 2026-08-20 and Ollama Cloud routes are policy-OUT per `SUBSCRIPTIONS.yaml`. Credentials never cross between lanes.
- Gemini is available only through AGY; Gemini CLI and direct-API wrappers are retired.
- MiniMax M3 is accessed through GJC as a backup.
- Kilo defaults to deepseek-v4-flash while account credit remains ($50/mo, resets the 15th); `kilo-free-auto` (`kilo/kilo-auto/free`) is used only once credits are exhausted. Kilo can also serve as a Kimi-K3 backup when the canonical Kimi account runs out of usage. The rotating monthly `:free` models must be verified live before use; never silently substitute lanes.
- Call GLM through ZCode (`zcode -p`), not Claude Code. See `docs/ZCODE.md`.
- Do not default visual-QA / screenshot work to GLM/ZCode. Prefer a dedicated vision lane unless the user named GLM for eyes.
- When native search is missing or unreliable, use the globally configured DuckDuckGo `ddg` MCP. Never fabricate search results.
- Atomic mechanical work routes to the Dell only when the brief is genuinely
  narrow; repository-wide, multi-file, risky, architectural, migration, and
  security-sensitive signals escalate before the mechanical keyword check.

## Local Qwen NUC Safety

Two models are resident simultaneously on the NUC (champion `:46380`, ornith
`:46381`; together ~44/64GB GTT with ~20GB margin). GPU-window laws apply — no
bench traffic against the residents. The on-demand qwen35/qwen36 rotation and
its load/restore lifecycle were attic'd on 2026-08-20 and must not be restored;
auto-routed local work is carried by the residents now.

## GLM is ZCode here

The official Anthropic subscription is not an active provider lane. **Agents
call GLM through ZCode** (`zcode -p`). Opus, Sonnet, and Haiku are not
Dispatch executors.

The global `claude` → `bin/claude-glm52` symlink is **legacy** for the
`zai-glm` executor only. `claude-real` remains the stock Claude Code binary
for harness maintenance. Do not teach `claude -p` as the GLM path.

## Authentication

- Codex executors use the logged-in ChatGPT subscription session, not an OpenAI API key.
- `zai-glm` and `zai-glm-flash` use `Z_AI_API_KEY` or the corresponding macOS Keychain / `pass` entry; the flash lane's runtime auth lives inside its isolated flash-home config and the key rotates with the main ZCode config.
- Grok uses the official CLI's browser/OAuth session or `XAI_API_KEY`.
- Kimi, AGY, GJC, Kilo, and LM Studio use their native harness authentication (`kilo_api_key` in Keychain for Kilo's gateway lane).
- `xiaomi-mimo` uses Keychain `xiaomi_api_key` sent as an `api-key` header, never Bearer.
- `command-code` uses the authenticated commandcode.ai CLI session (Pro plan).
- `deepseek-v4-pro` prefers the DeepSeek platform key (Keychain `deepseek_api_key`, `api.deepseek.com`) and falls back to the Ollama Cloud key.
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
Moonshot Anthropic-compatible Kimi, direct MiniMax, Gemini CLI, and
legacy direct Gemini API lanes are retired. Attic'd on 2026-08-20 and in the
`SUBSCRIPTIONS.yaml` retired list: `unsloth-nucbox`, the on-demand
`qwen35-*` / `qwen36-*` locals (superseded by the nucbox residents),
`kimi-k3-ollama` / Ollama Cloud routes (policy-OUT), AGY Pro, and the old
xiaomi-mimo key lane. Historical handoffs and plans may mention them, but they
are not operational instructions.
