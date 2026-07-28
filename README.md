# Pushing Dispatch_

Multi-model dispatch for AI coding agents. One harness, many models.

An orchestrator model dispatches worker agents with custom briefs and custom system prompts across multiple providers via a unified CLI. Workers get identical tool access, status reporting, and context loading regardless of provider.

## Why

AI coding agents work best when you separate **judgment** from **execution**. The orchestrator stays in one seat, makes decisions, and fans out mechanical work to an appropriate executor selected by the routing policy for each subtask.

The problem: every provider has a different CLI and different tool-use semantics. Multiple models mean multiple sets of integration bugs.

The fix: route supported providers through their appropriate agentic harnesses and shared dispatch protocols. One shared library handles argument parsing, context loading, stream parsing, status writing, and worker lifecycle. Each provider is a thin wrapper that selects its endpoint and execution path.

## The Four Pillars

### 1. The Harness Flip

Providers use their supported agentic harnesses through a common dispatch layer. One status protocol and one context-loading pattern span the executors.

Adding a new provider = one shell wrapper + one TOML entry.

### 2. Brief-Only Context Loading

Workers don't inherit the orchestrator's full context. A brief declares what context it needs using named "packs" from a registry. The wrapper resolves and concatenates: baseline rules + declared packs + task body.

Workers see only what they need. A lint script enforces that shared config stays small.

### 3. Matrix-Driven Routing

A single TOML config (`dispatch_matrix.toml`) encodes every executor's capabilities, allowed modes, cost caps, and routing preferences. The auto-router reads the brief (size, keywords, complexity), applies its routing heuristics, and selects the first capable, available executor in the matrix's ordered candidate lists.

The matrix is the source of truth for executor capabilities, allowed modes, cost caps, and routing preferences; the auto-router supplies the small mode and keyword classification layer.

### 4. Nested Dispatch with Safety Rails

Workers can spawn sub-workers. Budget cascades from parent (no independent quotas, that is a multiplication attack). A permissions matrix prevents self-dispatch (loop risk), cost-asymmetric chains, and leaf models from orchestrating.

Kill propagation walks the tree bottom-up. No auto-retry on failure. Ever.

## Quick Start

```bash
# 1. Clone and configure
git clone <repository-url>
cd <checkout-directory>
cp dispatch_matrix.toml.example dispatch_matrix.toml

# 2. Check prerequisites
bash bin/check-prereqs.sh

# 3. Configure at least one supported provider using its documented credential mechanism

# 4. Write a brief
cat > /tmp/my-brief.md << 'EOF'
---
title: Fix lint warnings
executor: <configured-executor>
---
Fix all ESLint warnings in src/utils.js
EOF

# 5. Dispatch
python cli.py task start --executor <configured-executor> --task-file /tmp/my-brief.md --cwd /path/to/project

# 6. Check status
python cli.py list --active
python cli.py status <worker-id>
```

## Supported Providers

Executor names, provider capabilities, routing modes, and setup requirements are defined by the checked-in example matrix and the configured provider wrappers. See [docs/PROVIDERS.md](docs/PROVIDERS.md) for configuration details.

### Local fleet leaf (when present)

When this checkout includes the NUCBox/Ornith overlay, see [ops/unsloth-nucbox/README.md](ops/unsloth-nucbox/README.md) for the sticky local coding leaf and related launch notes. Routing still comes from the matrix and provider docs; do not treat local fleet material as required on every mirror snapshot.

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
    status_writer.py               # Atomic worker status files
    stream_parser.py               # Stream-json event parsing
  bin/
    wrappers/                     # Provider wrappers
      _exec.sh                    # Shared execution library
      executor_prompt.md          # Worker prompt template
      *.sh                        # Provider and harness wrappers
    check-prereqs.sh              # Environment verification
    smoke-test.sh                 # First-run validation
  dispatch_packs/                 # Context packs for brief assembly
    _baseline.md                  # Universal worker rules
    _registry.toml                # Pack name -> file mapping
    *.md                          # Detail packs
  hooks/                          # Agent hooks
  commands/                       # Slash commands
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
- [CLAUDE.md](CLAUDE.md) -- Claude Code orientation
- [AGENTS.md](AGENTS.md) -- OpenAI Codex / generic agent orientation
- [GEMINI.md](GEMINI.md) -- Gemini tooling orientation

## Core Principle

Judgment stays in one place (the orchestrator seat). Execution fans out to an appropriate executor selected by the routing policy for each subtask. The brief is the contract. The matrix is the source of truth. Everything else is plumbing.

## Quick start with Claude Code

The fastest setup path: open a fresh Claude Code session, paste this:

```
Read SETUP_WITH_CLAUDE.md from this checkout and walk me through setup end to end.
```

The session will check your prerequisites, help you pick providers, generate your matrix config, run a smoke test, and wire up the advisor pattern in your project. See [SETUP_WITH_CLAUDE.md](SETUP_WITH_CLAUDE.md) for the full runbook.

## License

[MIT](LICENSE)

## Made by

[Pushing Squares](https://pushingsquares.com) -- workflow engineering for creative tooling.

GitHub: [@PUSHINGSQUARES](https://github.com/PUSHINGSQUARES)
