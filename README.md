# Pushing Dispatch_

Multi-model dispatch for AI coding agents. One harness, many models.

An orchestrator model dispatches worker agents with custom briefs and custom system prompts across multiple providers via a unified CLI. Workers get identical tool access, status reporting, and context loading regardless of provider.

## Why

AI coding agents work best when you separate **judgment** from **execution**. The orchestrator stays in one seat, makes decisions, and fans out mechanical work to the cheapest model that can handle each subtask.

The problem: every provider has a different CLI, different tool-use semantics, different context loading. Three models means three sets of bugs.

The fix: route every provider through a small wrapper with the same brief, status, and logging contract. API-key providers use compatible HTTP endpoints; CLI-login providers such as Codex and Kimi use their native CLIs.

## The Four Pillars

### 1. The Harness Flip

Every provider (Anthropic, Kimi, DeepSeek, MiniMax, Codex, local models) runs through the same Dispatch contract. One set of briefs, one status protocol, one context-loading pattern.

Adding a new provider = one shell wrapper + one TOML entry.

### 2. Brief-Only Context Loading

Workers don't inherit the orchestrator's full context. A brief declares what context it needs using named "packs" from a registry. The wrapper resolves and concatenates: baseline rules + declared packs + task body.

Workers see only what they need. A lint script enforces that shared config stays small.

### 3. Matrix-Driven Routing

A single TOML config (`dispatch_matrix.toml`) encodes every executor's capabilities, allowed modes, cost caps, and routing preferences. The auto-router reads the brief (size, keywords, complexity) and picks the cheapest model that can handle it.

No hardcoded if/else chains. The matrix is the source of truth.

### 4. Nested Dispatch with Safety Rails

Workers can spawn sub-workers. Budget cascades from parent (no independent quotas, that is a multiplication attack). A permissions matrix prevents self-dispatch (loop risk), cost-asymmetric chains, and leaf models from orchestrating.

Kill propagation walks the tree bottom-up. No auto-retry on failure. Ever.

## Quick Start

```bash
# 1. Clone and configure
git clone https://github.com/YOUR_ORG/pushing-dispatch.git
cd pushing-dispatch
cp dispatch_matrix.toml.example dispatch_matrix.toml

# 2. Install global routing commands and check prerequisites
bash bin/install-global-routing.sh
bash bin/check-prereqs.sh

# 3. Set up at least one provider
export ANTHROPIC_API_KEY="sk-ant-..."
# Or use CLI/OAuth providers:
kimi login
# Or third-party API-key providers:
export DEEPSEEK_API_KEY="sk-..."

# 4. Write a brief
cat > /tmp/my-brief.md << 'EOF'
---
title: Fix lint warnings
---
Fix all ESLint warnings in src/utils.js
EOF

# 5. Ask Dispatch which executor is best/cost-efficient, or let it auto-pick
pushing-dispatch route --mode task --task-file /tmp/my-brief.md
pushing-dispatch task start --executor auto --task-file /tmp/my-brief.md --cwd /path/to/project

# 6. Check status
pushing-dispatch list --active
pushing-dispatch status <worker-id>
```

## Supported Providers

| Provider | Executor | Endpoint | Context Window |
|----------|----------|----------|----------------|
| Anthropic (Claude Opus) | `opus` | Native | 200K |
| Anthropic (Claude Sonnet) | `sonnet` | Native | 200K |
| Anthropic (Claude Haiku) | `haiku` | Native | 200K |
| Kimi Coding API | `kimi-coding` | Anthropic-compat | 256K |
| Kimi CLI OAuth | `kimi-moonshot` | Kimi CLI | 262K |
| DeepSeek | `deepseek` | Anthropic-compat | 128K |
| Z.ai | `zai-glm`, `zai-air` | Anthropic-compat | 128K |
| MiniMax | `minimax`, `minimax-m25*` | Anthropic/OpenAI-compat | 128K-200K |
| OpenAI/Codex | `openai-*`, `codex-spark`, `codex` | Codex CLI | 200K |
| Gemini | `gemini-*` | Gemini API | 1M |
| Kilo Gateway | `kilo-*` | OpenAI-compat | model-dependent |
| LM Studio / local | `lm-studio`, `codex-oss` | OpenAI/Codex local | model-dependent |

See [docs/PROVIDERS.md](docs/PROVIDERS.md) for configuration details per provider.

## Repo Structure

```
pushing-dispatch/
  cli.py                          # Main CLI entry point
  breakout.py                     # Worktree session manager
  skeleton_lint.py                # CLAUDE.md line-count enforcement
  dispatch_matrix.toml.example    # Reference executor matrix
  dispatch_lib/                   # Core library
    auto_router.py                # Brief-to-executor routing
    budget.py                     # Spend tracking (JSONL ledger)
    context_budget.py             # Context window pre-flight
    cost_calc.py                  # Per-provider cost calculation
    feature_flag.py               # Nested dispatch rollout gates
    matrix_validator.py           # Matrix TOML validation
    nested.py                     # Tree-walk, kill cascade, spend rollup
    path_conventions.py           # Standardized artifact paths
    permissions.py                # Nested dispatch permissions
    status_writer.py              # Atomic worker status files
    stream_parser.py              # Stream-json event parsing
  bin/
    wrappers/                     # Provider wrappers
      _exec.sh                    # Shared execution library
      executor_prompt.md          # Worker prompt template
      sonnet.sh, opus.sh, ...     # One per provider
    check-prereqs.sh              # Environment verification
    smoke-test.sh                 # First-run validation
  dispatch_packs/                 # Context packs for brief assembly
    _baseline.md                  # Universal worker rules
    _registry.toml                # Pack name -> file mapping
    *.md                          # Detail packs
  hooks/                          # Claude Code hooks
    auto_poll.sh                  # Auto-polling injection
  commands/                       # Slash commands
    dispatch-poll.md              # Polling cycle
  docs/                           # Documentation
  examples/                       # Worked example briefs
```

## Documentation

- [INSTALL.md](INSTALL.md) -- step-by-step installation
- [docs/ORCHESTRATING.md](docs/ORCHESTRATING.md) -- complete orchestrator guide
- [docs/CUSTOMIZATION.md](docs/CUSTOMIZATION.md) -- per-user customization recipes
- [docs/PROVIDERS.md](docs/PROVIDERS.md) -- provider-specific configuration
- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) -- common gotchas
- [CONTRIBUTING.md](CONTRIBUTING.md) -- how to contribute

## For LLM Agents

This repo includes orientation files for AI coding agents:
- [CLAUDE.md](CLAUDE.md) -- for Claude Code sessions
- [AGENTS.md](AGENTS.md) -- for OpenAI Codex / generic agents
- [GEMINI.md](GEMINI.md) -- for Gemini CLI sessions

## Core Principle

Judgment stays in one place (the orchestrator seat). Execution fans out to the cheapest model that can handle each subtask. The brief is the contract. The matrix is the source of truth. Everything else is plumbing.

## Quick start with Claude Code

The fastest setup path: open a fresh Claude Code session, paste this:

```
Read SETUP_WITH_CLAUDE.md from https://github.com/PUSHINGSQUARES/Pushing-Dispatch_ and walk me through setup end to end.
```

The session will check your prereqs, help you pick providers, generate your matrix config, run a smoke test, and wire up the advisor pattern in your project. See [SETUP_WITH_CLAUDE.md](SETUP_WITH_CLAUDE.md) for the full runbook.

## Self-healing & availability

Routing is availability-aware: `route` and `task start --executor auto` only
return an executor that is actually reachable. Set up once with:

```bash
bash bin/sync-credentials.sh   # consolidate provider keys into the Keychain
pushing-dispatch doctor        # live table of reachable / cooldown / re-login lanes
```

When a worker hits an auth, rate-limit, or network error its lane is demoted
into a cooldown and the router automatically reroutes to the next candidate;
the lane recovers on cooldown expiry or the next success. State persists across
sessions in `availability.json` and `lane_health.json`. Each dispatch's outcome
is appended to `outcomes.jsonl` (the substrate for the opt-in learning loop).

## License

[MIT](LICENSE)

## Made by

[Pushing Squares](https://pushingsquares.com) -- workflow engineering for creative tooling.

GitHub: [@PUSHINGSQUARES](https://github.com/PUSHINGSQUARES)
