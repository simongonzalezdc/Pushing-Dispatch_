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

**Context window:** 200K tokens (all tiers)

**Thinking tokens:**
- Opus: default 4000, ceiling 16000
- Sonnet: default 4000, ceiling 16000
- Haiku: default 0 (disabled), ceiling 2000

**Cost model:** Subscription-based. Token counts tracked for visibility but cost shows as $0.00 in the budget ledger (unless using API key billing).

**Caveats:**
- Rules engine and hooks fire normally (not `--bare`)
- CLAUDE.md auto-discovery is active (keep it small via skeleton_lint.py)

## Moonshot (Kimi K2.6)

### Executors: kimi, kimi-think

**Endpoint:** `https://api.moonshot.ai/anthropic` (Anthropic-compatible)

**Auth:**
```bash
export MOONSHOT_API_KEY="sk-..."
```

**Bare mode:** On (`CE_BARE_MODE=1`). Workers see only baseline + brief + packs.

**Context window:** 256K tokens (the largest available, ideal for long-context tasks)

**Thinking tokens:**
- `kimi`: 0 (thinking disabled, for mechanical work)
- `kimi-think`: 4000 default, 8000 ceiling (for hard problems)

**Cost model:** Metered. Approximately $1.00/M input, $3.00/M output (verify current pricing at platform.moonshot.cn).

**Routing guidance:**
- Long-context tasks (>50K tokens): prefer `kimi`
- Mechanical refactors, doc generation: prefer `kimi`
- Hard coding problems where Sonnet over-thinks: try `kimi-think`

**Caveats:**
- `temperature` and `top_p` are fixed when thinking is enabled (setting them returns an API error)
- `tool_choice` limited to `"auto"` or `"none"` with thinking enabled
- Rules engine does not fire (hooks disabled by `--bare`)
- Max turns capped at 25 by default (configurable in matrix)

## DeepSeek

### Executor: deepseek

**Endpoint:** `https://api.deepseek.com/anthropic` (Anthropic-compatible)

**Auth:**
```bash
export DEEPSEEK_API_KEY="sk-..."
```

**Bare mode:** On (`CE_BARE_MODE=1`)

**Context window:** 128K tokens

**Thinking tokens:** Default 4000, ceiling 8000

**Cost model:** Metered. Approximately $0.50/M input, $2.00/M output (verify at platform.deepseek.com).

**Routing guidance:**
- Pure-code tasks with strong type/test signals: prefer `deepseek`
- Good alternative to Sonnet for mechanical coding

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
| Context window | 200K | 256K | 128K |
| Bare mode | No (OAuth) | Yes | Yes |
| Hooks fire | Yes | No | No |
| CLAUDE.md loads | Yes (skeleton) | No | No |
| Thinking tokens | Up to 16K | Up to 8K | Up to 8K |
| Cost model | Subscription/API | Metered | Metered |
| Nested dispatch | Yes | Yes | Yes |
| Max turns default | Unlimited | 25 | 25 |
