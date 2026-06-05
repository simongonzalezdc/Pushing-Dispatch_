# Provider Configuration

## Anthropic (Claude)

### Executors: opus, sonnet, haiku

**Endpoint:** Native (no ANTHROPIC_BASE_URL override needed)

**Auth:** Anthropic API key or Claude Code subscription

```bash
# Option A: API key
export ANTHROPIC_API_KEY="sk-ant-api03-..."

# Option B: Subscription auth
claude login
```

**Bare mode:** Off (`CE_BARE_MODE=0`). Anthropic providers use normal Claude Code mode because subscription OAuth requires it. Workers auto-load the project CLAUDE.md (which should be skeletonized to stay small).

**Context window:**
- Opus 4.7: 1M tokens (1M-context plan) or 200K (standard tier)
- Sonnet 4.6: 200K standard, 1M with the `context-1m-2025-08-07` beta header
- Haiku 4.5: 200K

**Thinking tokens:**
- Opus: default 4000, ceiling 16000
- Sonnet: default 4000, ceiling 16000
- Haiku: default 0 (disabled), ceiling 2000

**Cost model:** Subscription-based. Token counts tracked for visibility but cost shows as $0.00 in the budget ledger (unless using API key billing).

**Caveats:**
- Rules engine and hooks fire normally (not `--bare`)
- CLAUDE.md auto-discovery is active (keep it small via skeleton_lint.py)

## Kimi CLI OAuth

### Executor: kimi-moonshot

**Endpoint:** Kimi Code CLI native OAuth path (`kimi`)

**Auth:**
```bash
kimi login
```

Dispatch checks `~/.kimi/credentials/kimi-code.json` for a refresh token or
unexpired access token. It does not require `MOONSHOT_API_KEY`.

**Execution mode:** Native Kimi CLI print mode. Workers see baseline + brief +
packs through the shared Dispatch wrapper.

The wrapper isolates Kimi with a temporary `KIMI_SHARE_DIR` by default,
symlinking only `config.toml` and the OAuth `credentials/` directory while
providing an empty `mcp.json`. This keeps global Kimi MCP/search/browser tools
out of Dispatch workers. Set `KIMI_CLI_ISOLATE_SHARE=0` to opt back into the
normal global Kimi share dir.

**Context window:** 262K tokens, matching the local Kimi CLI config.

**Thinking tokens:**
- Managed by the Kimi CLI/model config.

**Cost model:** OAuth/subscription path; Dispatch records worker outcomes but
does not require local API-key cost accounting for this lane.

**Routing guidance:**
- Use when you explicitly want the local Kimi CLI lane or need the existing Kimi
  OAuth account.
- Long-context automatic routing currently prefers `kimi-coding` first because
  the API wrapper has a lighter startup path.

**Caveats:**
- The wrapper uses a bounded timeout (`KIMI_CLI_TIMEOUT_SECONDS`, default 600s)
  so a stuck worker is marked errored instead of hanging forever.

## DeepSeek

### Executor: deepseek

**Endpoint:** `https://api.deepseek.com/anthropic` (Anthropic-compatible)

**Auth:**
```bash
export DEEPSEEK_API_KEY="sk-..."
```

**Bare mode:** On (`CE_BARE_MODE=1`)

**Context window:** 1M tokens (DeepSeek V4)

**Default model:** `deepseek-v4-flash` (cheap, mechanical work). Swap to `deepseek-v4-pro` in the matrix for harder reasoning.

**Thinking tokens:** Default 4000, ceiling 8000

**Cost model:** Metered. As of 2026-04-27 (verify at platform.deepseek.com):
- V4-flash: ~$0.14/M input, ~$0.28/M output
- V4-pro (75% promo through 2026-05-05): ~$0.435/M input, ~$0.87/M output. Post-promo: multiply by 4.
- V4-pro cache hit: ~$0.0036/M input

**Routing guidance:**
- Pure-code tasks with strong type/test signals: prefer `deepseek` (v4-flash)
- Good alternative to Sonnet for mechanical coding
- Long-context summarization: V4's 1M window competes with Kimi's 256K

**Caveats:**
- Same `--bare` limitations as Kimi (no hooks, no rules engine)
- Max turns capped at 25 by default

## Adding a New Provider

Any provider that exposes an Anthropic-compatible API endpoint can be added in under 30 minutes. See [CUSTOMIZATION.md](CUSTOMIZATION.md) for the step-by-step recipe.

Requirements for a new provider:
1. Anthropic-compatible `/v1/messages` endpoint
2. Support for `ANTHROPIC_AUTH_TOKEN` header (or equivalent)
3. Tool-use support in the API response format

## Provider Comparison Matrix

| Feature | Anthropic | Moonshot | DeepSeek |
|---------|-----------|----------|----------|
| Context window | 200K, 1M (Opus, Sonnet w/ beta) | 256K | 1M (V4) |
| Bare mode | No (OAuth) | Yes | Yes |
| Hooks fire | Yes | No | No |
| CLAUDE.md loads | Yes (skeleton) | No | No |
| Thinking tokens | Up to 16K | Up to 8K | Up to 8K |
| Cost model | Subscription/API | Metered | Metered |
| Nested dispatch | Yes | Yes | Yes |
| Max turns default | Unlimited | 25 | 25 |
